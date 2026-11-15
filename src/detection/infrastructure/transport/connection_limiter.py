"""Tope de conexiones simultáneas y cancelación de todas al cerrar."""

from __future__ import annotations

import asyncio


class ConnectionLimiter:
    """Solo se usa desde el event loop: no necesita locks."""

    def __init__(self, max_connections: int):
        self.max_connections = max_connections
        self.rejected = 0
        self._tasks: set[asyncio.Task] = set()

    def admit(self, task: asyncio.Task) -> bool:
        """Registra la conexión; si ya hay ``max_connections``, la cuenta como rechazada."""
        if len(self._tasks) >= self.max_connections:
            self.rejected += 1
            return False
        self._tasks.add(task)
        return True

    def release(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)

    async def cancel_all(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def __len__(self) -> int:
        return len(self._tasks)


class SensorSlots:
    """Tope de conexiones simultáneas por sensor autenticado.

    Evita que un solo token acapare el cupo global. Solo se usa desde el event
    loop: no necesita locks.
    """

    def __init__(self, per_sensor: int):
        self.per_sensor = per_sensor
        self.rejected = 0
        self._open: dict[str, int] = {}

    def acquire(self, sensor_id: str) -> bool:
        count = self._open.get(sensor_id, 0)
        if count >= self.per_sensor:
            self.rejected += 1
            return False
        self._open[sensor_id] = count + 1
        return True

    def release(self, sensor_id: str) -> None:
        count = self._open.get(sensor_id, 0) - 1
        if count > 0:
            self._open[sensor_id] = count
        else:
            self._open.pop(sensor_id, None)

    def count(self, sensor_id: str) -> int:
        return self._open.get(sensor_id, 0)
