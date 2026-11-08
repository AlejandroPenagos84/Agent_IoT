from __future__ import annotations


def make_client(client_id: str, username: str | None = None,
                password: str | None = None, tls: dict | None = None):
    """Create a paho client compatible with paho MQTT 1.x and 2.x."""
    import paho.mqtt.client as mqtt

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,
                             client_id=client_id)
    except (AttributeError, TypeError):
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
    if tls:
        client.tls_set(**tls)
    if username:
        client.username_pw_set(username, password)
    return client
