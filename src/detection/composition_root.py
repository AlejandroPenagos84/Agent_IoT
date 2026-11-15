from __future__ import annotations

import os
import ssl
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from detection.application import Agent, BrokerPool, DetectionServer
from detection.application.use_cases.ingest_alert import IngestAlert
from detection.infrastructure.classifiers import TcpXgbClassifier
from detection.infrastructure.repositories.registry_sqlite import RegistryStore
from detection.infrastructure.sensor_tokens import SensorTokenService
from detection.infrastructure.sinks import (
    CompositeAlertSink,
    FileEvidenceSink,
    IngestAlertSink,
    MqttAlertSink,
)
from detection.infrastructure.transport import (
    AsyncSocketServer,
    CertificateReloader,
    server_ssl_context,
)
from detection.infrastructure.transport.sensor_identity import SensorIdentity

BINARY_LABELS = {'normal', 'ataque'}


@dataclass
class AgentConfig:
    """Runtime settings used to assemble the detector application."""

    capture_endpoint: str = 'unix:///capture/features.sock'
    model_dir: str | None = None
    # Publicación opcional de alertas por MQTT; None = sin MQTT.
    broker_host: str | None = None
    username: str | None = None
    password: str | None = None
    normal_labels: Sequence[str] = ('normal',)
    alert_port: int = 1883
    alert_topic: str = 'alertas/deteccion'
    evidence_dir: str = '/evidence'
    evidence_seconds: float = 30.0
    evidence_max_bytes: int = 500 * 1024 * 1024
    # Segundos sin repetir alerta del mismo flujo (None = 5 s).
    alert_cooldown: float | None = None
    # Transporte y paralelismo por broker.
    queue_size: int = 10_000
    max_connections: int = 10_000
    max_workers: int = 256
    worker_idle_seconds: float = 600.0
    # TLS de producción (solo aplica a endpoints tls://).
    tls_cert: str | None = None
    tls_key: str | None = None
    tls_ca: str | None = None
    require_sensor_token: bool = True

    @classmethod
    def from_env(cls) -> AgentConfig:
        """Read the agent settings from ``AGENT_*`` environment variables."""
        env = os.getenv
        return cls(
            capture_endpoint=env('CAPTURE_ENDPOINT', cls.capture_endpoint),
            model_dir=env('MODEL_DIR') or None,
            broker_host=env('ALERT_MQTT_HOST') or None,
            alert_port=int(env('ALERT_MQTT_PORT', '1883')),
            username=env('ALERT_MQTT_USERNAME') or None,
            password=env('ALERT_MQTT_PASSWORD') or None,
            alert_topic=env('ALERT_MQTT_TOPIC', cls.alert_topic),
            evidence_dir=env('EVIDENCE_DIR', cls.evidence_dir),
            tls_cert=env('TLS_CERT') or None,
            tls_key=env('TLS_KEY') or None,
            tls_ca=env('TLS_CA') or None,
        )


"""
Composition root: the single place where the concrete adapters are assembled and
injected into the Agent. No selection logic; just wiring.
"""


def _server_ssl_context(cfg: AgentConfig) -> ssl.SSLContext | None:
    return server_ssl_context(cfg.capture_endpoint, cfg.tls_cert, cfg.tls_key, cfg.tls_ca)


def build_agent(
    cfg: AgentConfig,
    ingest: IngestAlert,
    sensor_tokens: SensorTokenService | None = None,
    registry: RegistryStore | None = None,
) -> DetectionServer:
    """Build the transport, the per-broker pool and its shared sinks.

    ``ingest`` is the same use case the API uses, so alerts go straight to the
    database and the daily journal, in-process. ``sensor_tokens`` validates the
    hello frame on ``tls://`` endpoints; with ``registry`` the agent also rejects
    (and later disconnects) sensors that were deleted or revoked.
    """
    probe = TcpXgbClassifier(model_dir=cfg.model_dir)
    class_names = set(getattr(probe, 'cfg', {}).get('class_names', []))
    if class_names != BINARY_LABELS:
        raise ValueError(
            'El agente espera artefactos binarios normal/ataque; '
            f'pipeline_config.json declara {sorted(class_names)}. '
            'Reentrena y exporta desde 03_modelo_tcp.ipynb.'
        )
    sinks = [IngestAlertSink(ingest)]
    if cfg.broker_host:
        sinks.append(
            MqttAlertSink(
                cfg.broker_host,
                port=cfg.alert_port,
                topic=cfg.alert_topic,
                username=cfg.username,
                password=cfg.password,
            )
        )
    sink = CompositeAlertSink(sinks)
    evidence = FileEvidenceSink(cfg.evidence_dir, max_bytes=cfg.evidence_max_bytes)
    cooldown = 5.0 if cfg.alert_cooldown is None else cfg.alert_cooldown

    def agent_factory(source):
        return Agent(
            source=source,
            classifier=TcpXgbClassifier(model_dir=cfg.model_dir),
            sink=sink,
            evidence_sink=evidence,
            evidence_seconds=cfg.evidence_seconds,
            window_size=1,
            normal_labels=cfg.normal_labels,
            source_name='tshark-tcp',
            per_flow=True,
            alert_cooldown=cooldown,
            server_ports=(1883, 8883),
        )

    pool = BrokerPool(
        agent_factory,
        max_workers=cfg.max_workers,
        queue_size=cfg.queue_size,
        idle_seconds=cfg.worker_idle_seconds,
    )
    require_token = cfg.require_sensor_token and cfg.capture_endpoint.startswith('tls://')
    validator = None
    if require_token:
        if sensor_tokens is None:
            raise ValueError('El endpoint TLS requiere AUTH_JWT_SECRET')
        validator = sensor_tokens.decode
    ssl_context = _server_ssl_context(cfg)
    closeables: list = [sink]
    if ssl_context is not None:
        reloader = CertificateReloader(ssl_context, cfg.tls_cert, cfg.tls_key)
        reloader.start()
        closeables.append(reloader)
    server = AsyncSocketServer(
        cfg.capture_endpoint,
        max_connections=cfg.max_connections,
        ssl_context=ssl_context,
        token_validator=validator,
        require_token=require_token,
        sensor_active=_sensor_active(registry) if require_token and registry else None,
    )
    return DetectionServer(server, pool, closeables=tuple(closeables))


def _sensor_active(registry: RegistryStore) -> Callable[[SensorIdentity], bool]:
    def check(identity: SensorIdentity) -> bool:
        return registry.sensor_token_active(
            identity.tenant_id, identity.broker_id, identity.sensor_id, identity.issued_at
        )

    return check
