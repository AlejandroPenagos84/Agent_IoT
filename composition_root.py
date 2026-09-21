from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from application import Agent
from infrastructure.classifiers import HybridClassifier, AnomalyClassifier, XgbClassifier
from infrastructure.sinks import MqttAlertSink
from infrastructure.tshark.tshark_feature_source import TsharkFeatureSource

BINARY_LABELS = {'normal', 'ataque'}


@dataclass
class AgentConfig:
    """Runtime settings used to assemble the detector application."""
    capture_path: str = '/capture/features.jsonl'
    capture_poll: float = 0.05
    capture_from_start: bool = False
    model_dir: str | None = None
    broker_host: str = 'localhost'
    username: str | None = None
    password: str | None = None
    window_size: int = 11
    window_per_flow: bool = True
    l2_episode_gap_seconds: float = 1.0
    normal_labels: Sequence[str] = ('normal',)
    alert_port: int = 1883
    alert_topic: str = 'alertas/deteccion'
    model: str = 'hybrid'


'''
Composition root: the single place where the concrete adapters are assembled and
injected into the Agent. No selection logic; just wiring.
'''


def build_agent(cfg: AgentConfig) -> Agent:
    """Build the application and inject its concrete infrastructure adapters."""
    classifiers = {'hybrid': HybridClassifier, 'lstm': AnomalyClassifier,
                   'xgboost': XgbClassifier}
    if cfg.model not in classifiers:
        raise ValueError(f'Modelo desconocido: {cfg.model}. Usar hybrid, lstm o xgboost')
    classifier = classifiers[cfg.model](model_dir=cfg.model_dir)
    artifact = getattr(classifier, 'cfg', {})
    if artifact.get('feature_mode') != 'mqtt':
        raise ValueError('El agente MQTT necesita artefactos feature_mode=mqtt. '
                         'Reentrena y exporta desde el notebook actualizado.')
    if artifact.get('observation_mode') != 'ethernet_tcp_and_l2':
        raise ValueError('El agente necesita artefactos entrenados con la población '
                         'Ethernet TCP+L2. Reentrena y exporta desde el notebook '
                         'actualizado.')
    class_names = set(artifact.get('class_names', []))
    if class_names != BINARY_LABELS:
        raise ValueError('El agente espera artefactos binarios normal/ataque; '
                         f'pipeline_config.json declara {sorted(class_names)}. '
                         'Reentrena y exporta desde el notebook actualizado.')
    return Agent(
        source=TsharkFeatureSource(path=cfg.capture_path,
                                   from_start=cfg.capture_from_start,
                                   poll=cfg.capture_poll),
        classifier=classifier,
        sink=MqttAlertSink(cfg.broker_host, port=cfg.alert_port,
                           topic=cfg.alert_topic, username=cfg.username,
                           password=cfg.password),
        window_size=cfg.window_size,
        normal_labels=cfg.normal_labels,
        source_name='tshark',
        per_flow=cfg.window_per_flow,
        l2_episode_gap_seconds=float(
            artifact.get('l2_episode_gap_seconds', cfg.l2_episode_gap_seconds)),
    )
