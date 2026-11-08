# Alert sinks

Alert sinks implement the `AlertSink` port
(`application/ports/ports_out.py`). The agent knows only this interface, so a
new destination can be added without changing the use case.

## Alert schema

All sinks serialize `domain.model.Alert.to_dict()`:

```json
{
  "alert_id": "6f7b0f2c-3a1d-4f5e-9c3b-1f2a4d5e6f70",
  "ts": 1789563240.5,
  "kind": "class",
  "label": "DoS",
  "client_id": null,
  "ip": "10.0.0.5",
  "topic": "home/salon/luz",
  "mse": null,
  "source": "tshark-tcp"
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
to MQTT, persists a daily JSONL copy and, when `ALERT_API_URL` is set, posts to
the detection API. It is thread-safe because workers for different brokers share
one instance.

### `HttpAlertSink`

Posts `Alert.to_dict()` to the detection API with `Authorization: Bearer`. It
uses a bounded queue and a background thread, so a slow API never blocks
detection. Failed deliveries are retried a few times, counted and logged; the
daily JSONL sink remains the local fallback. In production use an HTTPS URL and
set `ALERT_API_CA` if the API uses a private CA.

## Evidence sinks

Evidence sinks implement the `EvidenceSink` port. The agent buffers the raw
frames of the last 30 seconds per connection (`tcp.stream` + sorted endpoints,
the same key as the alert cooldown) and writes them when an alert is emitted.

### `FileEvidenceSink`

Writes `<directory>/YYYY-MM-DD/<alert_id>.jsonl`, using the UTC date of the
write. The first line is the alert (including `alert_id`), followed by one raw
record per line. Writes are atomic (`.tmp` + `os.replace`). When the directory
exceeds `max_bytes` (500 MB by default), it stops writing and logs a warning;
alerts keep flowing. The ETL deletes whole date folders by age.
