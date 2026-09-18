from __future__ import annotations

import json
import os
import time
from typing import Iterator

from application.ports.ports_out import FeatureSource
from application.ports.types import FeatureRow, Frame
from domain.model import FrameContext

from .tshark_schema import FEATURE_COLUMNS, NETWORK_COLUMNS

DEFAULT_CAPTURE = '/capture/features.jsonl'
MAX_TRACKED_FLOWS = 4096


def _to_float(value: object, default: float = -1.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _to_optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


'''
FeatureSource for the tshark JSONL capture. Tails the file, reassembles partial
lines, decodes each record, extracts the numeric features and resolves the frame
context, yielding Frame objects.
'''

class TsharkFeatureSource(FeatureSource):
    """Tail capture JSONL and yield application ``Frame`` objects."""
    def __init__(self, path: str = DEFAULT_CAPTURE, from_start: bool = False,
                 poll: float = 0.05, dstport: int = 1883) -> None:
        """Configure the file path, start position, poll interval, and fallback port."""
        self.path = path
        self.from_start = from_start
        self.poll = poll
        self.dstport = dstport
        self._offset = 0
        self._stop = False
        self._partial = ''
        self._client_ids: dict = {}
        self._last_topics: dict = {}

    def start(self) -> None:
        """Reset the reader and select EOF or the beginning as its start."""
        self._offset = 0 if self.from_start else self._size()
        self._stop = False
        self._client_ids.clear()
        self._last_topics.clear()

    def stop(self) -> None:
        """Request termination of the tail loop."""
        self._stop = True

    def _size(self) -> int:
        """Return the current file size, treating a missing file as empty."""
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def _features(self, record: dict) -> FeatureRow:
        """Extract and normalize the model's numeric feature columns."""
        return {key: (_to_float(record.get(key)) if key in NETWORK_COLUMNS
                      else record.get(key)) for key in FEATURE_COLUMNS}

    @staticmethod
    def _remember(store: dict, stream_id: int, value) -> None:
        """Store a per-stream value, evicting the oldest stream past the limit."""
        store[stream_id] = value
        while len(store) > MAX_TRACKED_FLOWS:
            store.pop(next(iter(store)))

    def _resolve_flow(self, record: dict, stream_id) -> tuple:
        """Resolve client_id/topic, remembering CONNECT and the last topic per stream.

        MQTT PUBLISH does not carry the publisher's client_id and not every frame
        carries a topic, so both are cached per ``tcp.stream`` and reused for later
        frames of the same connection. Without ``tcp.stream`` there is no state.
        """
        client_id = record.get('mqtt.clientid') or None
        topic = record.get('mqtt.topic') or None
        if stream_id is None:
            return client_id, topic
        if client_id:
            # mqtt.clientid solo aparece en CONNECT; se recuerda para el resto del flujo.
            self._remember(self._client_ids, stream_id, client_id)
        else:
            client_id = self._client_ids.get(stream_id)
        if topic:
            self._remember(self._last_topics, stream_id, topic)
        else:
            topic = self._last_topics.get(stream_id)
        return client_id, topic

    def _context(self, record: dict) -> FrameContext:
        """Extract alert metadata, correlating identity and topic per connection."""
        stream_id = (_to_int(record['tcp.stream'])
                     if record.get('tcp.stream') is not None else None)
        client_id, topic = self._resolve_flow(record, stream_id)
        return FrameContext(
            ts=_to_optional_float(record.get('frame.time_epoch')),
            client_id=client_id,
            ip=record.get('ip.src') or None,
            topic=topic,
            srcport=_to_int(record.get('tcp.srcport'), 0),
            dstport=_to_int(record.get('tcp.dstport'), self.dstport),
            dst_ip=record.get('ip.dst') or None,
            stream_id=stream_id,
        )

    def rows(self) -> Iterator[Frame]:
        """Yield complete JSON records while the source is running."""
        while not self._stop:
            if self._offset > self._size():
                self._offset = 0
                self._client_ids.clear()
                self._last_topics.clear()
            try:
                with open(self.path, 'r', encoding='utf-8', errors='replace') as handle:
                    handle.seek(self._offset)
                    chunk = handle.read()
                    self._offset = handle.tell()
            except FileNotFoundError:
                chunk = ''
            if not chunk:
                time.sleep(self.poll)
                continue
            lines = (self._partial + chunk).split('\n')
            self._partial = lines.pop()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield Frame(features=self._features(record),
                            context=self._context(record))
