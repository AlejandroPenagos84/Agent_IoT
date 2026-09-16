from __future__ import annotations

from dataclasses import dataclass, field

FEATURE_COLUMNS = (
    'frame.time_delta',
    'frame.time_delta_displayed',
    'frame.time_relative',
    'frame.len',
    'frame.cap_len',
    'tcp.srcport',
    'tcp.dstport',
)

FeatureRow = dict[str, float]

ALERT_KIND_CLASS = 'class'
ALERT_KIND_ANOMALY = 'anomaly'
ALERT_KIND_INTRUSION = 'intrusion'


@dataclass(frozen=True, slots=True)
class ClientMeta:
    client_id: str
    ip: str
    srcport: int
    dstport: int


@dataclass(frozen=True, slots=True)
class ConnectionEvent:
    ts: float
    client_id: str
    ip: str
    srcport: int
    dstport: int
    username: str | None = None
    anonymous: bool = False


@dataclass(frozen=True, slots=True)
class Alert:
    ts: float
    kind: str
    label: str
    client_id: str | None = None
    ip: str | None = None
    topic: str | None = None
    mse: float | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        return {
            'ts': self.ts,
            'kind': self.kind,
            'label': self.label,
            'client_id': self.client_id,
            'ip': self.ip,
            'topic': self.topic,
            'mse': self.mse,
            'source': self.source,
        }
