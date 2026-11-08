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

        def on_connect(client, userdata, flags, rc, *extra):
            self._connection_rc = rc
            connected.set()

        self._client.on_connect = on_connect

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
