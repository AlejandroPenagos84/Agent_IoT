"""Ventanas deslizantes de features: una global o una por sentido de cada flujo."""

from __future__ import annotations

from collections import deque

from detection.application.ports.types import FeatureRow
from detection.domain.flow_keys import direction_key
from detection.domain.model import FrameContext

_GLOBAL = object()


class SlidingWindows:
    """Acumula features y entrega la ventana cuando tiene ``size`` frames.

    - ``per_flow=True``: una ventana por ``direction_key``; los frames sin
      endpoints completos no se aceptan.
    - ``per_flow=False``: una sola ventana para todo el stream.
    """

    def __init__(self, size: int, per_flow: bool = True):
        self.size = size
        self.per_flow = per_flow
        self._buffers: dict = {}

    def accepts(self, context: FrameContext) -> bool:
        return not self.per_flow or direction_key(context) is not None

    def push(self, context: FrameContext, features: FeatureRow) -> list[FeatureRow] | None:
        """Agrega el frame; devuelve la ventana completa o ``None`` si aún no se llena."""
        key = direction_key(context) if self.per_flow else _GLOBAL
        if key is None:
            return None

        buffer = self._buffers.get(key)
        if buffer is None:
            buffer = self._buffers[key] = deque(maxlen=self.size)

        buffer.append(features)
        if len(buffer) < self.size:
            return None
        return list(buffer)
