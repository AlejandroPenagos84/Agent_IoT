"""Puerto: API central que inscribe sensores y renueva sus tokens."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EnrollmentApi(ABC):
    """Ambos métodos lanzan ``EnrollmentError`` si la API rechaza la credencial
    y ``OSError``/``ValueError`` si la red o la respuesta fallan."""

    @abstractmethod
    def enroll(self, enrollment_key: str, name: str) -> dict:
        """Cuerpo de ``/sensors/enroll``: identidad, secreto, endpoint, CA y token."""

    @abstractmethod
    def refresh(self, sensor_secret: str) -> dict:
        """Cuerpo de ``/sensors/token/refresh``: ``access_token`` y ``expires_in``."""
