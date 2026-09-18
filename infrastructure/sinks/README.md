# `sinks/` — Alert Sinks

Destinos de alertas. Implementan el ABC `AlertSink`
(`application/ports/ports_out.py`, `emit(alert: Alert) -> None`). Patrón **Strategy**:
el agente solo conoce la interfaz, así que añadir un sink nuevo (p. ej. un reporte LLM)
no toca el orquestador.

## Esquema de la alerta

Todos serializan `domain.model.Alert.to_dict()`:

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

## `mqtt_alert.py` — `MqttAlertSink`

`MqttAlertSink(host, port=1883, topic='alertas/deteccion', client_id='agente-alertas', username=None, password=None, tls=None, qos=0, retain=False, keepalive=60)`

- Crea el cliente con `mqtt_utils.make_client` (paho 1.x/2.x) y lo conecta en el
  constructor (`loop_start()`).
- `emit(alert)`: publica el JSON en `topic`; guarda `last_rc` (código de retorno).
- `close()`: `loop_stop()` + `disconnect()`.
- El import de `paho` es lazy (dentro de `make_client`). El sink **no** cierra solo al
  terminar el agente (`Agent.stop()` solo detiene la fuente).

## `file_alert.py` — `FileAlertSink`

`FileAlertSink(path, flush=True)`

- Crea el directorio destino si no existe.
- `emit(alert)`: anexa una línea **JSON Lines** por alerta.
- `flush=True` fuerza el volcado a disco tras cada escritura (útil para ver en vivo).

## `__init__.py`

Reexporta `FileAlertSink` y `MqttAlertSink`. El `composition_root` inyecta
`MqttAlertSink`; `FileAlertSink` se puede añadir a mano (no hay `CompositeAlertSink` en
el refactor actual).
