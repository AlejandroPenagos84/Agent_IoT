from __future__ import annotations

import json
import os

from core.types import Alert


class FileAlertSink:
    def __init__(self, path: str, flush: bool = True):
        self.path = path
        self.flush = flush
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def emit(self, alert: Alert) -> None:
        with open(self.path, 'a') as handle:
            handle.write(json.dumps(alert.to_dict()) + '\n')
            if self.flush:
                handle.flush()
