from __future__ import annotations

from collections.abc import Iterable

from application.ports.ports_out import AlertSink
from domain.model import Alert


class CompositeAlertSink(AlertSink):
    """Deliver each alert to every configured sink."""

    def __init__(self, sinks: Iterable[AlertSink]):
        self.sinks = tuple(sinks)

    def emit(self, alert: Alert) -> None:
        for sink in self.sinks:
            sink.emit(alert)

    def close(self) -> None:
        """Close sinks that expose a lifecycle method."""
        for sink in self.sinks:
            close = getattr(sink, 'close', None)
            if close is not None:
                close()
