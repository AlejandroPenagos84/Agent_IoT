from __future__ import annotations

from typing import Sequence

from core.protocols import AlertSink
from core.types import Alert


class CompositeAlertSink:
    def __init__(self, sinks: Sequence[AlertSink]):
        self.sinks = list(sinks)

    def emit(self, alert: Alert) -> None:
        for sink in self.sinks:
            sink.emit(alert)
