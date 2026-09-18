from __future__ import annotations

import json
import os

from application.ports.ports_out import AlertSink
from domain.model import Alert

class FileAlertSink(AlertSink):
    """Append each alert as one JSON object per line."""
    def __init__(self, path: str, flush: bool = True):
        """Configure the output path and whether each write is flushed."""
        self.path = path
        self.flush = flush
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def emit(self, alert: Alert) -> None:
        """Serialize and append one alert."""
        with open(self.path, 'a') as handle:
            handle.write(json.dumps(alert.to_dict()) + '\n')
            if self.flush:
                handle.flush()
