from __future__ import annotations

from detection.application.ports.types import FeatureRow
from detection.domain.model import FrameContext

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


def _remember(store: dict, stream_id: int, value) -> None:
    """Store a per-stream value, evicting the oldest stream past the limit."""
    store[stream_id] = value
    while len(store) > MAX_TRACKED_FLOWS:
        store.pop(next(iter(store)))


class RecordParser:
    """Turn wire records into model features and alert context.

    MQTT PUBLISH does not carry the publisher's client_id and not every frame
    carries a topic, so both are cached per ``tcp.stream`` and reused for later
    frames of the same connection.
    """

    def __init__(self, dstport: int = 1883) -> None:
        self.dstport = dstport
        self._client_ids: dict = {}
        self._last_topics: dict = {}

    def reset(self) -> None:
        self._client_ids.clear()
        self._last_topics.clear()

    @staticmethod
    def features(record: dict) -> FeatureRow | None:
        """Return the precomputed TCP features, or ``None`` when out of scope."""
        precomputed = record.get('tcp_features')
        return dict(precomputed) if isinstance(precomputed, dict) else None

    def _resolve_flow(self, record: dict, stream_id) -> tuple:
        client_id = record.get('mqtt.clientid') or None
        topic = record.get('mqtt.topic') or None
        if stream_id is None:
            return client_id, topic
        key = (record.get('tenant_id'), record.get('broker_id'),
               record.get('sensor_id'), stream_id)
        if client_id:
            _remember(self._client_ids, key, client_id)
        else:
            client_id = self._client_ids.get(key)
        if topic:
            _remember(self._last_topics, key, topic)
        else:
            topic = self._last_topics.get(key)
        return client_id, topic

    def context(self, record: dict) -> FrameContext:
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
            tenant_id=record.get('tenant_id'),
            broker_id=record.get('broker_id'),
            sensor_id=record.get('sensor_id'),
        )
