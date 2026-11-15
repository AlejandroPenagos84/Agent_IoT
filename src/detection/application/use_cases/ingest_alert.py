"""Registrar una alerta detectada: base de datos + diario JSONL, una sola vez."""

from __future__ import annotations

from detection.application.ports.alert_repository import AlertRepository
from detection.application.ports.ports_out import AlertSink
from detection.domain.model import Alert


class IngestAlert:
    """Único camino de entrada de alertas, lo use el agente o la API.

    - Con ``tenant_id``: se guarda en el repositorio; si ya existía (mismo
      ``alert_id``) no se vuelve a escribir en ningún lado.
    - Sin ``tenant_id`` (captura local sin inscripción): no tiene dueño en la
      base, pero queda en el diario para el ETL.
    """

    def __init__(self, repository: AlertRepository, journal: AlertSink):
        self._repository = repository
        self._journal = journal

    def execute(self, alert: Alert) -> bool:
        stored = False
        if alert.tenant_id:
            stored = self._repository.add(alert)
            if not stored:
                return False
        self._journal.emit(alert)
        return stored
