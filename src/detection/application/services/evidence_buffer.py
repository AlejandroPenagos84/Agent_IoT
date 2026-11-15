"""Frames crudos recientes por conexión, para guardarlos cuando hay una alerta."""

from __future__ import annotations

from collections import deque

from detection.application.ports.ports_out import EvidenceSink
from detection.domain.flow_keys import connection_key
from detection.domain.model import Alert, FrameContext

MAX_EVIDENCE_FLOWS = 4096
MAX_EVIDENCE_RECORDS = 10_000


class EvidenceBuffer:
    """Guarda los últimos ``seconds`` (tiempo de captura) de cada conexión.

    Sin ``sink`` no guarda nada. La memoria está acotada: como mucho
    ``max_flows`` conexiones (se expulsa la más antigua) y ``max_records`` por
    conexión.
    """

    def __init__(
        self,
        sink: EvidenceSink | None,
        seconds: float,
        *,
        max_flows: int = MAX_EVIDENCE_FLOWS,
        max_records: int = MAX_EVIDENCE_RECORDS,
    ):
        self._sink = sink
        self.seconds = seconds
        self._max_flows = max_flows
        self._max_records = max_records
        self._buffers: dict = {}

    def remember(self, context: FrameContext, record: dict | None) -> None:
        if self._sink is None or record is None:
            return

        key = connection_key(context)
        buffer = self._buffers.get(key)
        if buffer is None:
            if len(self._buffers) >= self._max_flows:
                self._buffers.pop(next(iter(self._buffers)))
            buffer = self._buffers[key] = deque(maxlen=self._max_records)

        ts = context.ts
        if ts is not None:
            cutoff = ts - self.seconds
            while buffer and buffer[0][0] is not None and buffer[0][0] < cutoff:
                buffer.popleft()

        buffer.append((ts, record))

    def flush(self, alert: Alert, context: FrameContext) -> None:
        """Escribe la evidencia de la conexión que disparó ``alert``."""
        if self._sink is None:
            return

        key = connection_key(context)
        buffer = self._buffers.get(key)
        if not buffer:
            return

        cutoff = context.ts - self.seconds if context.ts is not None else None
        records = [record for ts, record in buffer if cutoff is None or ts is None or ts >= cutoff]
        if records:
            self._sink.write(alert, key, records)
