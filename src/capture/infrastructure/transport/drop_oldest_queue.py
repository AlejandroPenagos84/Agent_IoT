"""Cola acotada entre el hilo de tshark y el hilo que envía."""

from __future__ import annotations

import threading
from collections import deque


class DropOldestQueue:
    """Si se llena, descarta el registro más viejo: en un IDS en tiempo real
    importa más el tráfico reciente que completar el histórico."""

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._items: deque[str] = deque()
        self._cond = threading.Condition()
        self.dropped = 0

    def put(self, item: str) -> None:
        """Encola sin bloquear; si está llena, descarta el más viejo y suma ``dropped``."""
        with self._cond:
            if len(self._items) >= self.maxsize:
                self._items.popleft()
                self.dropped += 1

            self._items.append(item)
            self._cond.notify()

    def wait(self, timeout: float) -> bool:
        """Espera hasta ``timeout`` a que haya algo; devuelve si la cola tiene datos."""
        with self._cond:
            if not self._items:
                self._cond.wait(timeout)

            return bool(self._items)

    def take(self, n: int) -> list[str]:
        """Saca hasta ``n`` registros sin esperar."""
        with self._cond:
            count = min(n, len(self._items))
            return [self._items.popleft() for _ in range(count)]

    def wake_all(self) -> None:
        """Despierta a quien esté en ``wait`` (se usa al cerrar)."""
        with self._cond:
            self._cond.notify_all()

    def __len__(self) -> int:
        with self._cond:
            return len(self._items)
