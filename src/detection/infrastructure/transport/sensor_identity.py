"""Identidad de una conexión autenticada: la que trae el token del sensor."""

from __future__ import annotations

from dataclasses import dataclass

from wire.protocol import IDENTITY_KEYS


@dataclass(frozen=True)
class SensorIdentity:
    tenant_id: str
    broker_id: str
    sensor_id: str
    # Vencimiento del token (epoch); ``None`` si no trae ``exp``.
    expires_at: float | None = None
    # Emisión del token (epoch); sirve para invalidar tokens viejos al revocar.
    issued_at: float | None = None

    @classmethod
    def from_claims(cls, claims: dict) -> SensorIdentity:
        """Lanza ``KeyError``/``TypeError`` si faltan los ids."""
        ids = {key: str(claims[key]) for key in IDENTITY_KEYS}
        return cls(**ids, expires_at=_epoch(claims.get('exp')), issued_at=_epoch(claims.get('iat')))

    def bind(self, record: dict) -> bool:
        """Rellena los ids del registro con los del token.

        Devuelve ``False`` si el registro intenta usar otra identidad (suplantación).
        """
        for key in IDENTITY_KEYS:
            expected = getattr(self, key)
            value = record.get(key)
            if value is not None and str(value) != expected:
                return False
            record[key] = expected
        return True

    def remaining(self, now: float) -> float | None:
        """Segundos hasta el vencimiento, o ``None`` si no vence."""
        if self.expires_at is None:
            return None
        return self.expires_at - now


def _epoch(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
