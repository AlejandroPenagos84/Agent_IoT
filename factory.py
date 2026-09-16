from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from agent import Agent
from core.clock import SystemClock
from core.protocols import AlertSink, Classifier, FeatureSource, MetadataProvider
from rules import AnonymousConnectRule, AnyRule, ConnectionChurnRule
from sinks import CompositeAlertSink, FileAlertSink, MqttAlertSink
from sources import PlaintextMqttSource, TlsMqttSource

DEFAULT_TOPICS = ('home/#', 'admin/#', 'cmd/#')


@dataclass
class AgentConfig:
    source: str = 'plaintext'
    model: str = 'hybrid'
    model_dir: str | None = None
    broker_host: str = 'localhost'
    broker_port: int | None = None
    topics: Sequence[str] = DEFAULT_TOPICS
    username: str | None = None
    password: str | None = None
    keepalive: int = 60
    overhead: int = 54
    ca_certs: str | None = None
    certfile: str | None = None
    keyfile: str | None = None
    insecure: bool = False
    registry_path: str | None = None
    registry_from_start: bool = True
    window_size: int = 11
    normal_labels: Sequence[str] = ('normal',)
    alert_cooldown: float = 2.0
    alert_port: int = 1883
    alert_topic: str = 'alertas/deteccion'
    alert_file: str | None = None
    enable_intrusion_rules: bool = True


def _build_classifier(kind: str, model_dir: str | None) -> Classifier:
    if kind == 'hybrid':
        from classifiers import HybridClassifier
        return HybridClassifier(model_dir=model_dir)
    if kind == 'tls':
        from classifiers import TlsXgbClassifier
        return TlsXgbClassifier(model_dir=model_dir)
    if kind == 'case1':
        from classifiers import Case1Classifier
        return Case1Classifier(model_dir=model_dir)
    if kind == 'anomaly':
        from classifiers import AnomalyClassifier
        return AnomalyClassifier(model_dir=model_dir)
    raise ValueError(f'modelo desconocido: {kind}')


def build_source(cfg: AgentConfig, registry: MetadataProvider | None,
                 clock) -> FeatureSource:
    attributor = registry.attributor() if registry is not None else None
    port = cfg.broker_port or (8883 if cfg.source == 'tls' else 1883)
    common = dict(host=cfg.broker_host, port=port, topics=cfg.topics,
                  metadata=registry, attributor=attributor, clock=clock,
                  username=cfg.username, password=cfg.password,
                  keepalive=cfg.keepalive)
    if cfg.source == 'tls':
        return TlsMqttSource(ca_certs=cfg.ca_certs, certfile=cfg.certfile,
                             keyfile=cfg.keyfile, insecure=cfg.insecure, **common)
    if cfg.source == 'plaintext':
        return PlaintextMqttSource(overhead=cfg.overhead, **common)
    raise ValueError(f'fuente desconocida: {cfg.source}')


def build_sink(cfg: AgentConfig) -> AlertSink:
    sinks: list[AlertSink] = [
        MqttAlertSink(cfg.broker_host, port=cfg.alert_port, topic=cfg.alert_topic)
    ]
    if cfg.alert_file:
        sinks.append(FileAlertSink(cfg.alert_file))
    return sinks[0] if len(sinks) == 1 else CompositeAlertSink(sinks)


def build_agent(cfg: AgentConfig, source: FeatureSource | None = None,
                classifier: Classifier | None = None,
                sink: AlertSink | None = None,
                registry: MetadataProvider | None = None) -> Agent:
    clock = SystemClock()
    if registry is None and cfg.registry_path:
        from metadata import BrokerLogRegistry
        registry = BrokerLogRegistry(cfg.registry_path, clock=clock,
                                     from_start=cfg.registry_from_start,
                                     poll=0.05)
    if source is None:
        source = build_source(cfg, registry, clock)
    if classifier is None:
        classifier = _build_classifier(cfg.model, cfg.model_dir)
    if sink is None:
        sink = build_sink(cfg)
    rule = None
    if cfg.enable_intrusion_rules and registry is not None:
        rule = AnyRule([AnonymousConnectRule(), ConnectionChurnRule()])
    return Agent(source=source, classifier=classifier, sink=sink,
                 registry=registry, intrusion_rule=rule, clock=clock,
                 window_size=cfg.window_size, normal_labels=cfg.normal_labels,
                 source_name=cfg.source, alert_cooldown=cfg.alert_cooldown)
