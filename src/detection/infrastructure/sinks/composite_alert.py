from __future__ import annotations

import threading
from collections.abc import Iterable

from detection.application.ports.ports_out import AlertSink
from detection.domain.model import Alert


class CompositeAlertSink(AlertSink):
    """Deliver each alert to every configured sink."""

    def __init__(self, sinks: Iterable[AlertSink]):
        self.sinks = tuple(sinks)
        self._lock = threading.Lock()

    def emit(self, alert: Alert) -> None:
        with self._lock:
            for sink in self.sinks:
                sink.emit(alert)

    def close(self) -> None:
        """Close sinks that expose a lifecycle method."""
        with self._lock:
            for sink in self.sinks:
                close = getattr(sink, 'close', None)
                if close is not None:
                    close()
