"""Puerto: persistencia idempotente de alertas."""

from abc import ABC, abstractmethod

from detection.domain.model import Alert


class AlertRepository(ABC):
    @abstractmethod
    def add(self, alert: Alert) -> bool:
        """Guarda la alerta; ``False`` si su ``alert_id`` ya existía."""
