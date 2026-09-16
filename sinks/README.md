# `sinks/` — Alert Sinks

Destinos de alertas. Implementan el *port* `core.protocols.AlertSink`
(`emit(alert) -> None`).

Patrón: **Strategy** + **Composite** (`CompositeAlertSink`). Gracias a la interfaz, se
puede añadir un futuro `LlmReportSink` sin tocar el agente.

## Esquema de la alerta

Todas serializan `core.types.Alert.to_dict()`:

```json
{
  "ts": 1789563240.5,
  "kind": "class",
  "label": "DoS",
  "client_id": "atacante_flood",
  "ip": "192.168.20.42",
  "topic": "home/salon/luz",
  "mse": null,
  "source": "plaintext"
}
```

## `mqtt_alert.py` — `MqttAlertSink`

`MqttAlertSink(host, port=1883, topic='alertas/deteccion', client_id='agente-alertas', username=None, password=None, tls=None, qos=0, retain=False, keepalive=60)`

- Conecta al broker en el constructor (`make_client` compatible con paho 1.x/2.x) y
  arranca `loop_start()`.
- `emit(alert)`: publica el JSON en `topic`; guarda `last_rc` (código de retorno).
- `close()`: `loop_stop()` + `disconnect()`.
- paho se importa dentro del constructor (lazy).

## `file_alert.py` — `FileAlertSink`

`FileAlertSink(path, flush=True)`

- Crea el directorio destino si no existe.
- `emit(alert)`: anexa una línea **JSON Lines** por alerta.
- `flush=True` fuerza el volcado a disco tras cada escritura (útil para ver en vivo).

## `composite.py` — `CompositeAlertSink`

`CompositeAlertSink(sinks: Sequence[AlertSink])`

- Patrón **Composite**: reenvía cada alerta a **todos** los sinks configurados.
- `factory.build_sink` lo usa cuando hay sink MQTT + `--alert-file`.

## `__init__.py`

Reexporta `CompositeAlertSink`, `FileAlertSink` y `MqttAlertSink`.
