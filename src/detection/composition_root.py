from __future__ import annotations

import os
import ssl
import sys
import threading
from dataclasses import dataclass
from typing import Sequence

from detection.application import Agent, BrokerPool, DetectionServer
from detection.infrastructure.classifiers import TcpXgbClassifier
from detection.infrastructure.sinks import (
    CompositeAlertSink,
    DailyFileAlertSink,
    FileEvidenceSink,
    HttpAlertSink,
    MqttAlertSink,
)
from detection.infrastructure.tshark.async_socket_server import AsyncSocketServer

BINARY_LABELS = {'normal', 'ataque'}


@dataclass
class AgentConfig:
    """Runtime settings used to assemble the detector application."""
    capture_endpoint: str = 'unix:///capture/features.sock'
    model_dir: str | None = None
    broker_host: str = 'localhost'
    username: str | None = None
    password: str | None = None
    normal_labels: Sequence[str] = ('normal',)
    alert_port: int = 1883
    alert_topic: str = 'alertas/deteccion'
    alert_dir: str = '/alerts'
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
    jwt_secret: str | None = None
    require_sensor_token: bool = True
    # Alertas hacia la API Python (HTTPS o HTTP interno).
    alert_api_url: str | None = None
    alert_api_token: str | None = None
    alert_api_ca: str | None = None


'''
Composition root: the single place where the concrete adapters are assembled and
injected into the Agent. No selection logic; just wiring.
'''


class CertificateReloader:
    """Reload the server certificate when the files change (ACME renewals).

    ``SSLContext.load_cert_chain`` on the live context applies to new
    handshakes, so renewed certificates are used without restarting.
    """

    def __init__(self, context: ssl.SSLContext, cert: str, key: str,
                 interval: float = 3600.0):
        self.context, self.cert, self.key = context, cert, key
        self.interval = interval
        self._mtime = self._stamp()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='cert-reload',
                                        daemon=True)

    def _stamp(self) -> tuple[float, float]:
        try:
            return os.path.getmtime(self.cert), os.path.getmtime(self.key)
        except OSError:
            return (0.0, 0.0)

    def check(self) -> bool:
        stamp = self._stamp()
        if stamp == self._mtime or stamp == (0.0, 0.0):
            return False
        try:
            self.context.load_cert_chain(self.cert, self.key)
        except (OSError, ssl.SSLError) as exc:
            print(f'[agente] no se pudo recargar el certificado: {exc}',
                  file=sys.stderr, flush=True)
            return False
        self._mtime = stamp
        print('[agente] certificado TLS recargado', file=sys.stderr, flush=True)
        return True

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.check()

    def close(self) -> None:
        self._stop.set()


def _server_ssl_context(cfg: AgentConfig) -> ssl.SSLContext | None:
    if not cfg.capture_endpoint.startswith('tls://'):
        return None
    if not (cfg.tls_cert and cfg.tls_key):
        raise ValueError('El endpoint TLS requiere TLS_CERT y TLS_KEY')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cfg.tls_cert, cfg.tls_key)
    if cfg.tls_ca:
        context.load_verify_locations(cafile=cfg.tls_ca)
    return context


def _alert_api_token(cfg: AgentConfig):
    """Fixed ALERT_API_TOKEN, or an agent token renewed from AUTH_JWT_SECRET."""
    if cfg.alert_api_token:
        return cfg.alert_api_token
    secret = cfg.jwt_secret or os.getenv('AUTH_JWT_SECRET')
    if not secret:
        raise ValueError('ALERT_API_URL requiere ALERT_API_TOKEN o AUTH_JWT_SECRET')
    from detection.infrastructure.sensor_tokens import RenewingAgentToken

    return RenewingAgentToken(secret)


def build_agent(cfg: AgentConfig) -> DetectionServer:
    """Build the transport, the per-broker pool and its shared sinks."""
    probe = TcpXgbClassifier(model_dir=cfg.model_dir)
    class_names = set(getattr(probe, 'cfg', {}).get('class_names', []))
    if class_names != BINARY_LABELS:
        raise ValueError('El agente espera artefactos binarios normal/ataque; '
                         f'pipeline_config.json declara {sorted(class_names)}. '
                         'Reentrena y exporta desde 03_modelo_tcp.ipynb.')
    sinks = [
        MqttAlertSink(cfg.broker_host, port=cfg.alert_port,
                      topic=cfg.alert_topic, username=cfg.username,
                      password=cfg.password),
        DailyFileAlertSink(cfg.alert_dir),
    ]
    if cfg.alert_api_url:
        sinks.append(HttpAlertSink(cfg.alert_api_url, _alert_api_token(cfg),
                                   tls_ca=cfg.alert_api_ca))
    sink = CompositeAlertSink(sinks)
    evidence = FileEvidenceSink(cfg.evidence_dir,
                                max_bytes=cfg.evidence_max_bytes)
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

    pool = BrokerPool(agent_factory, max_workers=cfg.max_workers,
                      queue_size=cfg.queue_size,
                      idle_seconds=cfg.worker_idle_seconds)
    require_token = (cfg.require_sensor_token
                     and cfg.capture_endpoint.startswith('tls://'))
    validator = None
    if require_token:
        from detection.infrastructure.sensor_tokens import SensorTokenService

        secret = cfg.jwt_secret or os.getenv('AUTH_JWT_SECRET')
        if not secret:
            raise ValueError('El endpoint TLS requiere AUTH_JWT_SECRET')
        validator = SensorTokenService(secret).decode
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
    )
    return DetectionServer(server, pool, closeables=tuple(closeables))
