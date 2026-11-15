"""Puerto: de dónde salen los registros capturados (tshark en producción)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class PacketSource(ABC):
    @abstractmethod
    def open(self) -> None:
        """Arranca la captura; lanza ``CaptureStartError`` si no puede."""

    @abstractmethod
    def records(self) -> Iterator[dict]:
        """Un registro por frame, con los campos de ``CAPTURE_FIELDS``."""

    @abstractmethod
    def close(self) -> int:
        """Detiene la captura y devuelve su código de salida (0 si terminó bien)."""
