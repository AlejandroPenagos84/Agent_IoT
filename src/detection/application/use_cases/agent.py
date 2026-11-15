"""Caso de uso: detectar sobre un stream de frames y emitir las alertas anómalas."""

from __future__ import annotations

from collections.abc import Sequence

from detection.application.ports.ports_out import AlertSink, Classifier, EvidenceSink, FeatureSource
from detection.application.ports.types import Frame
from detection.application.services.evidence_buffer import EvidenceBuffer
from detection.application.services.sliding_windows import SlidingWindows
from detection.domain.alert_cooldown import AlertCooldown
from detection.domain.alert_factory import build_alert

DEFAULT_WINDOW = 11
DEFAULT_NORMAL_LABELS = ('normal',)
DEFAULT_EVIDENCE_SECONDS = 30.0


class Agent:
    """Coordina la detección; cada decisión la toma una pieza:

    - ``SlidingWindows``: arma la ventana (global o por sentido de cada flujo).
    - ``Classifier``: etiqueta la ventana.
    - ``AlertCooldown``: suprime la misma etiqueta repetida en la misma conexión.
    - ``build_alert``: arma la alerta reportando al cliente, no al broker.
    - ``EvidenceBuffer``: guarda los frames recientes y los escribe con la alerta.
    """

    def __init__(
        self,
        source: FeatureSource,
        classifier: Classifier,
        sink: AlertSink,
        window_size: int = DEFAULT_WINDOW,
        normal_labels: Sequence[str] = DEFAULT_NORMAL_LABELS,
        source_name: str = 'agente',
        per_flow: bool = True,
        alert_cooldown: float = 0.0,
        server_ports: Sequence[int] = (),
        evidence_sink: EvidenceSink | None = None,
        evidence_seconds: float = DEFAULT_EVIDENCE_SECONDS,
    ):
        """
        ``alert_cooldown``: segundos (tiempo de captura) sin repetir la misma
        etiqueta para la misma conexión; 0 = una alerta por ventana anómala.
        ``server_ports``: puertos del broker, para que la alerta reporte al
        cliente aunque el frame sea una respuesta broker -> cliente.
        """
        self.source = source
        self.classifier = classifier
        self.sink = sink
        self.normal_labels = set(normal_labels)
        self.source_name = source_name
        self.server_ports = frozenset(server_ports)
        self.windows = SlidingWindows(window_size, per_flow=per_flow)
        self.cooldown = AlertCooldown(alert_cooldown)
        self.evidence = EvidenceBuffer(evidence_sink, evidence_seconds)
        self.emitted = 0

    def run(self) -> None:
        """Arranca la fuente, consume frames y la detiene al salir."""
        self.source.start()
        try:
            for frame in self.source.rows():
                self.process(frame)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        self.source.stop()

    def process(self, frame: Frame) -> None:
        """Un frame: evidencia -> ventana -> clasificación -> alerta."""
        context = frame.context
        if not self.windows.accepts(context):
            return

        self.evidence.remember(context, frame.record)
        window = self.windows.push(context, frame.features)
        if window is None:
            return

        labels = self.classifier.predict(window)
        if not labels:
            return
        label = labels[-1]
        if label in self.normal_labels or self.cooldown.should_suppress(label, context):
            return

        alert = build_alert(label, context, source=self.source_name, server_ports=self.server_ports)
        self.sink.emit(alert)
        self.evidence.flush(alert, context)
        self.emitted += 1
