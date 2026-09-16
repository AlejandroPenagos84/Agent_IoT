from __future__ import annotations

import time
from typing import Callable, Iterator, Sequence

from core.protocols import Clock, MetadataProvider
from core.types import FeatureRow

from ._features import build_row, mqtt_packet_size
from ._stream import PahoMessageStream

DEFAULT_TOPICS = ('home/#', 'admin/#', 'cmd/#')


class PlaintextMqttSource:
    def __init__(self, host: str, port: int = 1883,
                 topics: Sequence[str] = DEFAULT_TOPICS,
                 client_id: str = 'agente-1883',
                 metadata: MetadataProvider | None = None,
                 attributor: Callable[[str, bytes], str | None] | None = None,
                 clock: Clock | None = None,
                 overhead: int = 54,
                 attribute_retries: int = 5,
                 attribute_wait: float = 0.05,
                 username: str | None = None,
                 password: str | None = None,
                 keepalive: int = 60):
        self.clock = clock
        self.metadata = metadata
        self.attributor = attributor
        self.overhead = overhead
        self.attribute_retries = attribute_retries
        self.attribute_wait = attribute_wait
        self.dstport = port
        self.last_context = None
        self._stream = PahoMessageStream(host, port, client_id, list(topics),
                                         clock, username=username,
                                         password=password, tls=None,
                                         keepalive=keepalive)

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def _client_id(self, topic: str, payload: bytes) -> str | None:
        if self.attributor is None:
            return None
        client_id = self.attributor(topic, payload)
        if client_id is None and self.metadata is not None:
            for _ in range(self.attribute_retries):
                time.sleep(self.attribute_wait)
                client_id = self.attributor(topic, payload)
                if client_id is not None:
                    break
        return client_id

    def _context(self, topic: str, payload: bytes) -> dict:
        client_id = self._client_id(topic, payload)
        meta = self.metadata.get(client_id) if (client_id and self.metadata) else None
        return {
            'client_id': client_id,
            'ip': meta.ip if meta else None,
            'topic': topic,
            'srcport': meta.srcport if meta else 0,
            'dstport': meta.dstport if meta else self.dstport,
        }

    def rows(self) -> Iterator[FeatureRow]:
        t0 = None
        prev = None
        for topic, payload, now in self._stream.messages():
            if t0 is None:
                t0 = now
            delta = 0.0 if prev is None else now - prev
            prev = now
            context = self._context(topic, payload)
            self.last_context = context
            size = mqtt_packet_size(topic, payload) + self.overhead
            yield build_row(now - t0, delta, size, size,
                            context['srcport'], context['dstport'])
