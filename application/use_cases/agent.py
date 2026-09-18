from __future__ import annotations

from collections import deque
from typing import Sequence

from application.ports.ports_out import Classifier, FeatureSource
from application.ports.ports_out import AlertSink
from domain.model import ALERT_KIND_CLASS, Alert, FrameContext

DEFAULT_WINDOW = 11
DEFAULT_NORMAL_LABELS = ('normal',)


'''
Orchestrator: consumes frames from the FeatureSource, builds the sliding
window, asks the Classifier and emits an Alert for non-normal labels.
'''


class Agent:
    """Run detection over a frame stream and emit anomalous classifications."""
    def __init__(self, source: FeatureSource, classifier: Classifier,
                 sink: AlertSink,
                 window_size: int = DEFAULT_WINDOW,
                 normal_labels: Sequence[str] = DEFAULT_NORMAL_LABELS,
                 source_name: str = 'agente',
                 per_flow: bool = True):
        """Create the use case with its driven ports injected."""
        self.source = source
        self.classifier = classifier
        self.sink = sink
        self.window_size = window_size
        self.normal_labels = set(normal_labels)
        self.source_name = source_name
        self.per_flow = per_flow
        self.emitted = 0

    def _emit(self, label: str, context: FrameContext) -> None:
        """Build and deliver an alert enriched with frame context."""
        self.sink.emit(Alert(
            ts=context.ts or 0.0, kind=ALERT_KIND_CLASS, label=label,
            client_id=context.client_id, ip=context.ip,
            topic=context.topic, source=self.source_name))
        self.emitted += 1

    def _classify_and_emit(self, window, context: FrameContext) -> None:
        """Classify a full window and suppress configured normal labels."""
        labels = self.classifier.predict(window)
        if not labels:
            return
        label = labels[-1]
        if label not in self.normal_labels:
            self._emit(label, context)

    def _consume_frames(self) -> None:
        """Read frames and maintain one global or per-flow buffer."""
        if not self.per_flow:
            buffer: deque = deque(maxlen=self.window_size)
            for frame in self.source.rows():
                buffer.append(frame.features)
                if len(buffer) < self.window_size:
                    continue
                self._classify_and_emit(list(buffer), frame.context)
            return
        buffers: dict = {}
        for frame in self.source.rows():
            context = frame.context
            # Directional connection: broker replies to different clients must
            # never share a buffer merely because their source port is 1883.
            # tcp.stream also separates successive connections reusing ports.
            if (not context.ip or not context.dst_ip
                    or not context.srcport or not context.dstport):
                continue
            key = (context.stream_id, context.ip, context.srcport,
                   context.dst_ip, context.dstport)
            buf = buffers.get(key)
            if buf is None:
                buf = buffers[key] = deque(maxlen=self.window_size)
            buf.append(frame.features)
            if len(buf) < self.window_size:
                continue
            self._classify_and_emit(list(buf), frame.context)

    def run(self) -> None:
        """Start the source, consume frames, and stop it on exit."""
        self.source.start()
        try:
            self._consume_frames()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the injected frame source."""
        self.source.stop()
