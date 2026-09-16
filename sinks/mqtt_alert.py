from __future__ import annotations

import json

from core.types import Alert


class MqttAlertSink:
    def __init__(self, host: str, port: int = 1883, topic: str = 'alertas/deteccion',
                 client_id: str = 'agente-alertas', username: str | None = None,
                 password: str | None = None, tls: dict | None = None,
                 qos: int = 0, retain: bool = False, keepalive: int = 60):
        from mqtt_utils import make_client

        self.topic = topic
        self.qos = qos
        self.retain = retain
        self.last_rc = None
        self._client = make_client(client_id, username=username,
                                   password=password, tls=tls)
        self._client.connect(host, port, keepalive)
        self._client.loop_start()

    def emit(self, alert: Alert) -> None:
        payload = json.dumps(alert.to_dict())
        info = self._client.publish(self.topic, payload, qos=self.qos,
                                    retain=self.retain)
        self.last_rc = info.rc

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
