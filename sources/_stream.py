from __future__ import annotations

import queue
import threading
from typing import Iterator

from core.protocols import Clock

Message = tuple[str, bytes, float]


class PahoMessageStream:
    def __init__(self, host: str, port: int, client_id: str, topics: list[str],
                 clock: Clock, username: str | None = None,
                 password: str | None = None, tls: dict | None = None,
                 keepalive: int = 60):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.topics = list(topics)
        self.clock = clock
        self.username = username
        self.password = password
        self.tls = tls
        self.keepalive = keepalive
        self._queue: queue.Queue[Message] = queue.Queue()
        self._client = None
        self._stopped = threading.Event()

    def start(self) -> None:
        from mqtt_utils import make_client

        self._stopped.clear()
        client = make_client(self.client_id, username=self.username,
                             password=self.password, tls=self.tls)
        client.on_message = self._on_message
        client.on_connect = self._on_connect
        client.connect(self.host, self.port, self.keepalive)
        client.loop_start()
        self._client = client

    def _on_connect(self, client, userdata, flags, rc):
        for topic in self.topics:
            client.subscribe(topic)

    def _on_message(self, client, userdata, msg):
        self._queue.put((msg.topic, bytes(msg.payload), self.clock.now()))

    def feed(self, topic: str, payload: bytes, ts: float | None = None) -> None:
        self._queue.put((topic, payload, self.clock.now() if ts is None else ts))

    def messages(self) -> Iterator[tuple[str, bytes, float]]:
        while not self._stopped.is_set():
            try:
                yield self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

    def stop(self) -> None:
        self._stopped.set()
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

