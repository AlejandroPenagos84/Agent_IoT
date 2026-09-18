from __future__ import annotations

from dataclasses import dataclass

from domain.model import FrameContext

"""Data contracts exchanged across application ports."""

FeatureRow = dict[str, float | int | str | None]


'''
Represents a captured frame: its network features plus the context
(client_id, ip, topic, ports) that enriches the emitted Alert.
'''
@dataclass(frozen=True, slots=True)
class Frame:
    """Network features and metadata for one captured frame."""
    features: FeatureRow
    context: FrameContext
