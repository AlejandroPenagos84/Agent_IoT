# Alert sinks

Alert sinks implement the `AlertSink` port
(`application/ports/ports_out.py`). The agent knows only this interface, so a
new destination can be added without changing the use case.

## Alert schema

All sinks serialize `domain.model.Alert.to_dict()`:

```json
{
  "ts": 1789563240.5,
  "kind": "class",
  "label": "DoS",
  "client_id": null,
  "ip": "10.0.0.5",
  "topic": "home/salon/luz",
  "mse": null,
  "source": "tshark"
}
```

## Implementations

### `MqttAlertSink`

Publishes JSON alerts to `alertas/deteccion` using Paho MQTT. It connects when
constructed, stores the last publish return code, and stops its network loop
when `close()` is called. TLS and credentials are optional.

### `FileAlertSink`

Appends one JSON object per line to a configured JSONL path and creates its
parent directory. `flush=True` makes alerts visible immediately.

### `DailyFileAlertSink`

Appends to `<directory>/YYYY-MM-DD.jsonl`, using the alert timestamp in UTC.
The schema is identical to the MQTT alert schema.

### `CompositeAlertSink`

Delivers each alert to every configured sink. The default composition publishes
to MQTT and persists a daily JSONL copy.
