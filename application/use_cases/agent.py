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
                 per_flow: bool = True,
                 alert_cooldown: float = 0.0,
                 server_ports: Sequence[int] = ()):
        """Create the use case with its driven ports injected."""
        self.source = source
        self.classifier = classifier
        self.sink = sink
        self.window_size = window_size
        self.normal_labels = set(normal_labels)
        self.source_name = source_name
        self.per_flow = per_flow
        # Segundos (tiempo de captura) sin repetir la misma etiqueta para el mismo
        # flujo; 0 = una alerta por ventana anómala.
        self.alert_cooldown = alert_cooldown
        # Puertos del servidor (broker): la alerta reporta al cliente, no al broker,
        # aunque el frame sea una respuesta broker -> cliente.
        self.server_ports = set(server_ports)
        self._last_alert: dict = {}
        self.emitted = 0

    def _emit(self, label: str, context: FrameContext) -> None:
        """Build and deliver an alert enriched with frame context."""
        ip = context.ip
        if context.srcport in self.server_ports and context.dst_ip:
            ip = context.dst_ip
        self.sink.emit(Alert(
            ts=context.ts or 0.0, kind=ALERT_KIND_CLASS, label=label,
            client_id=context.client_id, ip=ip,
            topic=context.topic, source=self.source_name))
        self.emitted += 1

    @staticmethod
    def _connection_key(context: FrameContext):
        """Both directions of one TCP connection share the cooldown."""
        endpoints = tuple(sorted(((str(context.ip), context.srcport),
                                  (str(context.dst_ip), context.dstport))))
        return context.stream_id, endpoints

    def _cooling_down(self, key, label: str, context: FrameContext) -> bool:
        """True if this connection already raised ``label`` within the cooldown.

        The handshake comes before CONNECT, so the first alert may lack client_id;
        once it is known, one more alert is allowed with the identity.
        """
        if self.alert_cooldown <= 0 or context.ts is None:
            return False
        key = (self._connection_key(context), context.client_id is not None)
        last = self._last_alert.get((key, label))
        if last is not None and context.ts - last < self.alert_cooldown:
            return True
        self._last_alert[(key, label)] = context.ts
        if len(self._last_alert) > 65536:
            self._last_alert.pop(next(iter(self._last_alert)))
        return False

    def _classify_and_emit(self, window, context: FrameContext, key=None) -> None:
        """Classify a full window and suppress configured normal labels."""
        labels = self.classifier.predict(window)
        if not labels:
            return
        label = labels[-1]
        if label not in self.normal_labels and not self._cooling_down(key, label, context):
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
            self._classify_and_emit(list(buf), frame.context, key)

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
