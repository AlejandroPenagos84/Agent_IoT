from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Sequence

from domain.model import Alert
from .types import FeatureRow, Frame

"""Driven ports invoked by application use cases."""

'''
Represents a source of captured frames. Each row carries its features together
with the context of the frame (Frame), so no mutable side-channel is needed.
'''
class FeatureSource(ABC):
    """Stream captured frames into the detection use case."""
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def rows(self) -> Iterator[Frame]: ...

    def stop(self) -> None:
        return None


'''
Represents the ML model that will be used to classify the data.
It defines a predict method that takes a sequence of FeatureRow
and returns a list of strings representing the predicted labels.
'''
class Classifier(ABC):
    """Classify one complete sliding window of feature rows."""
    @abstractmethod
    def predict(self, window: Sequence[FeatureRow]) -> list[str]: ...


'''
Represents a sink for emitting alerts.
'''
class AlertSink(ABC):
    """Deliver an alert to an external system."""
    @abstractmethod
    def emit(self, alert: Alert) -> None: ...
