"""Puerto: dónde persiste la identidad del sensor entre reinicios."""

from __future__ import annotations

from abc import ABC, abstractmethod

from capture.domain.sensor_state import SensorState


class SensorStateStore(ABC):
    @abstractmethod
    def load(self) -> SensorState | None:
        """Estado guardado, o ``None`` si no existe o está corrupto."""

    @abstractmethod
    def save(self, state: SensorState) -> None: ...

    @abstractmethod
    def save_ca(self, pem: str | None) -> None:
        """Guarda la CA del agente; ``None`` borra la anterior."""

    @property
    @abstractmethod
    def ca_path(self) -> str | None:
        """Ruta de la CA guardada, si hay una."""
