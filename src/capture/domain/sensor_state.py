"""Identidad persistida del sensor y reglas de su token."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def key_digest(key: str) -> str:
    """Huella de la clave de inscripción: detecta si el usuario pegó una clave nueva."""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


@dataclass
class SensorState:
    tenant_id: str
    broker_id: str
    sensor_id: str
    sensor_secret: str
    agent_endpoint: str
    agent_server_name: str
    refresh_interval_seconds: int
    enrollment_key_sha256: str
    access_token: str = ''
    expires_at: float = 0.0
    issued_at: float = 0.0
    revoked: bool = False

    def identity(self) -> dict:
        return {
            'tenant_id': self.tenant_id,
            'broker_id': self.broker_id,
            'sensor_id': self.sensor_id,
        }

    def enrolled_with(self, enrollment_key: str) -> bool:
        return self.enrollment_key_sha256 == key_digest(enrollment_key)

    def token_due(self, now: float) -> bool:
        """El token se cambia al pasar la mitad de su vida (o si no hay ninguno)."""
        lifetime = self.expires_at - self.issued_at
        return not self.access_token or now >= self.issued_at + lifetime / 2

    def adopt_token(self, token: str, expires_in: float, now: float) -> None:
        self.access_token = token
        self.issued_at = now
        self.expires_at = now + float(expires_in)
