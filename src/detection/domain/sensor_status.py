"""Estado de un sensor según su último heartbeat."""

from __future__ import annotations

from datetime import UTC, datetime

PENDING = 'pending'
CONNECTED = 'connected'
OFFLINE = 'offline'


def sensor_status(sensor: dict | None, online_seconds: int, now: datetime | None = None) -> str:
    """``pending`` si nunca se conectó, ``connected`` si se vio hace poco, si no ``offline``.

    Un sensor sin secreto (revocado al rotar la clave) está ``offline``.
    """
    if sensor is None or not sensor.get('last_seen'):
        return PENDING
    if not sensor.get('secret_hash'):
        return OFFLINE
    seen = datetime.fromisoformat(sensor['last_seen'])
    age = ((now or datetime.now(UTC)) - seen).total_seconds()
    return CONNECTED if age <= online_seconds else OFFLINE
