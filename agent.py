from __future__ import annotations

import threading
from collections import deque
from typing import Sequence

from core.clock import SystemClock
from core.protocols import (AlertSink, Classifier, Clock, FeatureSource,
                            IntrusionRule, MetadataProvider)
from core.types import ALERT_KIND_CLASS, Alert

DEFAULT_WINDOW = 11
DEFAULT_NORMAL_LABELS = ('normal',)


class Agent:
    def __init__(self, source: FeatureSource, classifier: Classifier,
                 sink: AlertSink,
                 registry: MetadataProvider | None = None,
                 intrusion_rule: IntrusionRule | None = None,
                 clock: Clock | None = None,
                 window_size: int = DEFAULT_WINDOW,
                 normal_labels: Sequence[str] = DEFAULT_NORMAL_LABELS,
                 source_name: str = 'agente',
                 alert_cooldown: float = 2.0):
        self.source = source
        self.classifier = classifier
        self.sink = sink
        self.registry = registry
        self.intrusion_rule = intrusion_rule
        self.clock = clock or SystemClock()
        self.window_size = window_size
        self.normal_labels = set(normal_labels)
        self.source_name = source_name
        self.alert_cooldown = alert_cooldown
        self.emitted = 0
        self._buffer: deque = deque(maxlen=window_size)
        self._last_alert: dict[str, float] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _context(self) -> dict:
        return getattr(self.source, 'last_context', None) or {}

    def _emit_class(self, label: str) -> None:
        now = self.clock.now()
        last = self._last_alert.get(label)
        if last is not None and (now - last) < self.alert_cooldown:
            return
        self._last_alert[label] = now
        context = self._context()
        self.sink.emit(Alert(
            ts=now, kind=ALERT_KIND_CLASS, label=label,
            client_id=context.get('client_id'), ip=context.get('ip'),
            topic=context.get('topic'), source=self.source_name))
        self.emitted += 1

    def _consume_frames(self) -> None:
        for row in self.source.rows():
            if self._stop.is_set():
                break
            self._buffer.append(row)
            if len(self._buffer) < self.window_size:
                continue
            labels = self.classifier.predict(list(self._buffer))
            if not labels:
                continue
            label = labels[-1]
            if label not in self.normal_labels:
                self._emit_class(label)

    def _consume_events(self) -> None:
        for event in self.registry.events():
            if self._stop.is_set():
                break
            if self.intrusion_rule is None:
                continue
            alert = self.intrusion_rule.check(event)
            if alert is not None:
                self.sink.emit(alert)
                self.emitted += 1

    def run(self) -> None:
        if self.registry is not None:
            self.registry.start()
            thread = threading.Thread(target=self._consume_events, daemon=True)
            thread.start()
            self._threads.append(thread)
        self.source.start()
        try:
            self._consume_frames()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        for component in (self.source, self.registry):
            stop = getattr(component, 'stop', None)
            if callable(stop):
                stop()
        for thread in self._threads:
            thread.join(timeout=2)
