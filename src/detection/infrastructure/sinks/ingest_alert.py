"""AlertSink del agente que entrega cada alerta al caso de uso IngestAlert."""

from detection.application.ports.ports_out import AlertSink
from detection.application.use_cases.ingest_alert import IngestAlert
from detection.domain.model import Alert


class IngestAlertSink(AlertSink):
    def __init__(self, ingest: IngestAlert):
        self._ingest = ingest

    def emit(self, alert: Alert) -> None:
        self._ingest.execute(alert)
