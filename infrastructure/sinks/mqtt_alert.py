from __future__ import annotations

import json

from application.ports.ports_out import AlertSink
from domain.model import Alert
from mqtt_utils import make_client

class MqttAlertSink(AlertSink):
    """Publish serialized alerts to an MQTT topic."""
    def __init__(self, host: str, port: int = 1883, topic: str = 'alertas/deteccion',
                 client_id: str = 'agente-alertas', username: str | None = None,
                 password: str | None = None, tls: dict | None = None,
                 qos: int = 0, retain: bool = False, keepalive: int = 60):
        """Connect a paho client and configure the alert publication policy."""

        self.topic = topic
        self.qos = qos
        self.retain = retain
        self.last_rc = None
        self._client = make_client(client_id, username=username,
                                   password=password, tls=tls)
        self._client.connect(host, port, keepalive)
        self._client.loop_start()

    def emit(self, alert: Alert) -> None:
        """Publish one alert and retain the broker return code."""
        payload = json.dumps(alert.to_dict())
        info = self._client.publish(self.topic, payload, qos=self.qos,
                                    retain=self.retain)
        self.last_rc = info.rc

    def close(self) -> None:
        """Stop the network loop and disconnect from the broker."""
        self._client.loop_stop()
        self._client.disconnect()
