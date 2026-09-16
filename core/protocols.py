from __future__ import annotations

from typing import Iterator, Protocol, Sequence, runtime_checkable

from .types import Alert, ClientMeta, ConnectionEvent, FeatureRow


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...


@runtime_checkable
class MetadataProvider(Protocol):
    def get(self, client_id: str) -> ClientMeta | None: ...
    def events(self) -> Iterator[ConnectionEvent]: ...


@runtime_checkable
class FeatureSource(Protocol):
    def start(self) -> None: ...
    def rows(self) -> Iterator[FeatureRow]: ...


@runtime_checkable
class Classifier(Protocol):
    def predict(self, window: Sequence[FeatureRow]) -> list[str]: ...


@runtime_checkable
class AlertSink(Protocol):
    def emit(self, alert: Alert) -> None: ...


@runtime_checkable
class IntrusionRule(Protocol):
    def check(self, event: ConnectionEvent) -> Alert | None: ...
