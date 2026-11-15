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
