"""Puerto: envío de registros NDJSON al agente."""

from __future__ import annotations

from abc import ABC, abstractmethod


class RecordSender(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def send(self, line: str) -> None:
        """Encola una línea NDJSON; no debe bloquear al que captura."""

    @abstractmethod
    def close(self, timeout: float = 2.0) -> None: ...
