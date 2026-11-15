"""Adaptador de AlertRepository sobre el RegistryStore SQLite."""

from detection.application.ports.alert_repository import AlertRepository
from detection.domain.model import Alert
from detection.infrastructure.repositories.registry_sqlite import RegistryStore


class SqliteAlertRepository(AlertRepository):
    def __init__(self, store: RegistryStore):
        self._store = store

    def add(self, alert: Alert) -> bool:
        return self._store.add_alert(alert.to_dict())
