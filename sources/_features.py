from __future__ import annotations

from core.types import FeatureRow

FIXED_HEADER = 2
TOPIC_LEN_PREFIX = 2


def remaining_length(n: int) -> int:
    size = 1
    while n >= 128:
        n //= 128
        size += 1
    return size


def mqtt_packet_size(topic: str, payload: bytes) -> int:
    topic_bytes = len(topic.encode('utf-8'))
    remaining = TOPIC_LEN_PREFIX + topic_bytes + len(payload)
    return FIXED_HEADER + remaining_length(remaining) + remaining


def build_row(time_relative: float, time_delta: float, frame_len: float,
              cap_len: float, srcport: float, dstport: float) -> FeatureRow:
    return {
        'frame.time_delta': float(time_delta),
        'frame.time_delta_displayed': float(time_delta),
        'frame.time_relative': float(time_relative),
        'frame.len': float(frame_len),
        'frame.cap_len': float(cap_len),
        'tcp.srcport': float(srcport),
        'tcp.dstport': float(dstport),
    }
