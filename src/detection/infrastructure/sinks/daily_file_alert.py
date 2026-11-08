from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from detection.application.ports.ports_out import AlertSink
from detection.domain.model import Alert


class DailyFileAlertSink(AlertSink):
    """Append alerts to one JSONL file per UTC calendar day."""

    def __init__(self, directory: str | Path, flush: bool = True):
        self.directory = Path(directory)
        self.flush = flush
        self.directory.mkdir(parents=True, exist_ok=True)

    def emit(self, alert: Alert) -> None:
        """Serialize an alert and append it to the file for its event date."""
        day = datetime.fromtimestamp(alert.ts, timezone.utc).date().isoformat()
        path = self.directory / f'{day}.jsonl'
        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(alert.to_dict()) + '\n')
            if self.flush:
                handle.flush()
