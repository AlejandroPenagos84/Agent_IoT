"""Regla anti-ráfaga: no repetir la misma etiqueta para la misma conexión."""

from __future__ import annotations

from .flow_keys import connection_key
from .model import FrameContext

MAX_TRACKED = 65536


class AlertCooldown:
    """Suprime alertas repetidas dentro de ``seconds`` (tiempo de captura).

    El handshake TCP llega antes del CONNECT, así que la primera alerta puede no
    tener ``client_id``; cuando se conoce, se permite una alerta más con la
    identidad. Con ``seconds <= 0`` o sin timestamp nunca suprime.
    """

    def __init__(self, seconds: float, max_tracked: int = MAX_TRACKED):
        self.seconds = seconds
        self._max_tracked = max_tracked
        self._last: dict = {}

    def should_suppress(self, label: str, context: FrameContext) -> bool:
        """``True`` si hay que callar la alerta; si no, registra este momento."""
        if self.seconds <= 0 or context.ts is None:
            return False

        key = ((connection_key(context), context.client_id is not None), label)
        last = self._last.get(key)
        if last is not None and context.ts - last < self.seconds:
            return True

        self._last[key] = context.ts
        if len(self._last) > self._max_tracked:
            self._last.pop(next(iter(self._last)))
        return False
