"""Real MQTT and dry-run publishers with lazy broker dependencies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Event
import time


class Publisher(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: str, qos: int = 0) -> int:
        """Publish a message and return the implementation result code."""

    @abstractmethod
    def stop(self) -> None:
        """Release publisher resources."""

    @abstractmethod
    def subscribe(self, topic_filter: str) -> None:
        """Subscribe for discovery; raise on rejection."""

    @abstractmethod
    def observed_topics(self) -> dict[str, str]:
        """Return topics and latest payloads actually received."""


class DryPublisher(Publisher):
    """No-op publisher used to validate scenarios without a broker."""

    def __init__(self, client_id):
        self.client_id = client_id

    def publish(self, topic, payload, qos=0):
        """Accept a message without opening a network connection."""
        return 0

    def stop(self):
        """Release no-op publisher resources."""
        pass

    def subscribe(self, topic_filter):
        pass

    def observed_topics(self):
        return {}


class MqttPublisher(Publisher):
    """Paho-backed publisher for one simulated MQTT client."""

    def __init__(self, client_id, host, port, username=None, password=None,
                 tls=None):
        """Connect and start the paho network loop."""
        from mqtt_utils import make_client

        self.client_id = client_id
        self._client = make_client(client_id, username=username,
                                   password=password, tls=tls)
        connected = Event()
        self._connection_rc = None
        self._pending = []
        self._observed = {}
        self._subscribed = Event()
        self._subscription_qos = None

        def on_connect(client, userdata, flags, rc, *extra):
            self._connection_rc = rc
            connected.set()

        self._client.on_connect = on_connect

        def on_message(client, userdata, message):
            self._observed[message.topic] = message.payload.decode('utf-8', errors='replace')

        def on_subscribe(client, userdata, mid, granted_qos, *extra):
            self._subscription_qos = granted_qos
            self._subscribed.set()

        self._client.on_message = on_message
        self._client.on_subscribe = on_subscribe
        try:
            self._client.connect(host, port, 60)
            self._client.loop_start()
            if not connected.wait(10):
                raise RuntimeError(f'{client_id}: timeout esperando CONNACK')
            if self._connection_rc != 0:
                raise RuntimeError(
                    f'{client_id}: conexión rechazada ({self._connection_rc})'
                )
        except Exception:
            self._client.disconnect()
            self._client.loop_stop()
            raise

    def publish(self, topic, payload, qos=0):
        """Publish one payload and return paho's result code."""
        info = self._client.publish(topic, payload, qos=qos)
        self._pending = [
            pending for pending in self._pending if not pending.is_published()
        ]
        if info.rc == 0:
            self._pending.append(info)
        return info.rc

    def stop(self):
        """Stop the paho loop and disconnect."""
        deadline = time.monotonic() + 10
        try:
            for info in self._pending:
                info.wait_for_publish(
                    timeout=max(0, deadline - time.monotonic())
                )
                if not info.is_published():
                    raise RuntimeError(
                        f'{self.client_id}: publicaciones pendientes al cerrar'
                    )
        finally:
            self._client.disconnect()
            self._client.loop_stop()

    def subscribe(self, topic_filter):
        self._subscribed.clear()
        rc, _ = self._client.subscribe(topic_filter, qos=0)
        if rc != 0 or not self._subscribed.wait(10):
            raise RuntimeError(
                f'{self.client_id}: error/timeout en SUBSCRIBE {topic_filter}'
            )
        if not self._subscription_qos or any(qos >= 128 for qos in self._subscription_qos):
            raise RuntimeError(
                f'{self.client_id}: suscripción rechazada a {topic_filter}'
            )

    def observed_topics(self):
        return self._observed.copy()
