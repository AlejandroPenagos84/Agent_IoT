"""Ventanas deslizantes causales de 5 s.

Replican ``_rolling_previous`` del entrenamiento: el valor del frame actual no
cuenta en su propia consulta; entra en la ventana en la consulta siguiente.
"""

from __future__ import annotations

import math
from collections import deque

WINDOW_SECONDS = 5.0


class RollingStats:
    """Conteo, suma y suma de cuadrados de los valores anteriores en la ventana."""

    __slots__ = ('_items', '_pending', 'count', 'total', 'squares')

    def __init__(self):
        # (t, valor) ya incluidos en la ventana.
        self._items = deque()

        # (t, valor) del frame anterior, todavía no incluido.
        self._pending = None

        self.count = 0
        self.total = 0.0
        self.squares = 0.0

    def advance(self, now: float, window: float = WINDOW_SECONDS) -> RollingStats:
        """Incluye el valor pendiente y expulsa los que tienen ``t <= now - window``."""
        if self._pending is not None:
            self._include(*self._pending)
            self._pending = None

        limit = now - window

        while self._items and self._items[0][0] <= limit:
            self._expire()

        return self

    def push(self, t: float, value: float) -> None:
        """Registra el valor del frame actual; cuenta desde la próxima consulta."""
        self._pending = (t, value)

    def mean(self) -> float:
        if self.count <= 0:
            return 0.0

        return self.total / self.count

    def std(self) -> float:
        """Desviación estándar poblacional (ddof=0)."""
        if self.count <= 0:
            return 0.0

        mean = self.total / self.count
        variance = self.squares / self.count - mean * mean

        return math.sqrt(max(variance, 0.0))

    def _include(self, t: float, value: float) -> None:
        self._items.append((t, value))

        self.count += 1
        self.total += value
        self.squares += value * value

    def _expire(self) -> None:
        _, value = self._items.popleft()

        self.count -= 1
        self.total -= value
        self.squares -= value * value


class EventCounter:
    """Número de eventos anteriores en la ventana (el actual no cuenta)."""

    __slots__ = ('_times',)

    def __init__(self):
        self._times = deque()

    def count(self, now: float, window: float = WINDOW_SECONDS) -> int:
        limit = now - window

        while self._times and self._times[0] <= limit:
            self._times.popleft()

        return len(self._times)

    def add(self, t: float) -> None:
        self._times.append(t)
