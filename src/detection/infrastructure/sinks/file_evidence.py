"""File-backed evidence adapter: one JSONL file per alert."""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from detection.application.ports.ports_out import EvidenceSink
from detection.domain.model import Alert

DEFAULT_MAX_BYTES = 500 * 1024 * 1024


class FileEvidenceSink(EvidenceSink):
    """Write evidence under ``<directory>/YYYY-MM-DD/<alert_id>.jsonl``.

    The date folder uses the UTC date of the write, not the frame clock, so the
    ETL can delete whole folders by age. The first line is the alert itself; the
    remaining lines are the raw frames of the connection.
    """

    def __init__(self, directory: str | Path, max_bytes: int = DEFAULT_MAX_BYTES):
        self.directory = Path(directory)
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    def _total_size(self) -> int:
        total = 0
        if not self.directory.exists():
            return 0
        for path in self.directory.rglob('*.jsonl'):
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def write(self, alert: Alert, key, records: Sequence[dict]) -> None:
        """Persist the alert and its frames unless the size cap is reached."""
        if not records:
            return
        with self._lock:
            if self._total_size() >= self.max_bytes:
                print('[evidence] tope de evidencia alcanzado; no se guarda '
                      f'{alert.alert_id}', file=sys.stderr, flush=True)
                return
            alert_id = alert.alert_id or str(uuid.uuid4())
            day = datetime.now(timezone.utc).date().isoformat()
            folder = self.directory / day
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'{alert_id}.jsonl'
            tmp = path.with_name(f'.{path.name}.tmp')
            try:
                with tmp.open('w', encoding='utf-8') as handle:
                    handle.write(json.dumps({'alert': alert.to_dict()},
                                            ensure_ascii=False) + '\n')
                    for record in records:
                        handle.write(json.dumps(record, ensure_ascii=False) + '\n')
                os.replace(tmp, path)
            finally:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
