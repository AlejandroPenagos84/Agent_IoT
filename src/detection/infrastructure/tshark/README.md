# `tshark` adapters

`stream_features.py` is the capture sidecar. It runs `tshark`, coerces the
selected fields, computes the TCP features and sends one NDJSON record per frame
to the agent over a Unix or TLS socket. It never writes frames to disk.

`socket_sender.py` (`SocketSender`) owns the socket on the capture side. `send`
only appends to a bounded queue; a daemon thread reconnects, batches and reports
how many records were sent, dropped or required a reconnect. Endpoints accept
`unix:///path` (development) or `tls://host:port` (production). In TLS mode it
sends `{"type":"hello","token":"<sensor-jwt>"}` before the first record and on
every reconnect; it waits for `{"type":"hello_ack"}` before sending features.

`async_socket_server.py` (`AsyncSocketServer`) accepts many connections from an
asyncio loop running in its own thread, parses NDJSON and routes each frame to
the per-broker worker pool. With `require_token` it validates the `hello` JWT,
replies `hello_ack`, binds the connection to its `tenant_id`, `broker_id` and
`sensor_id`, and rejects records that try to change that identity.
`record_parser.py` (`RecordParser`) is instantiated per connection.

`broker_pool.py` (application layer) creates one `Agent` worker per
`(tenant_id, broker_id)`, with its own bounded queue and classifier. A full
queue applies backpressure only to that broker's connections. Idle workers are
evicted after 10 minutes; the pool is capped at 256 workers.

`record_parser.py` (`RecordParser`) contains the parser shared by the source and
tests: it reads `tcp_features`, resolves the alert context and caches client ID
and topic per `tcp.stream`.

`tshark_schema.py` defines the tshark fields (`CAPTURE_FIELDS`) and the safe
record sent to the agent (`RECORD_FIELDS`). Passwords, usernames, payloads and
will fields are never requested.

`tcp_window_features.py` (`TcpWindowFeatures`) calcula en línea las 12 features TCP
del modelo B y `stream_features.py` las envía en cada registro como
`tcp_features` (dict en el orden de `TCP_FEATURE_COLUMNS`). Es el espejo incremental
de `ML_Model/data_preprocessing/tcp_features.py`: mismas ventanas causales de 5 s y
mismas claves de conexión (endpoints + nº de CONNECT) y dirección.
`tests/test_tcp_window_features.py` comprueba que coincide exactamente con la matriz
de entrenamiento sobre `DoS.csv`. Como el modelo se entrenó con la vista `mqtt`,
los frames sin puerto 1883/8883 no se envían ni entran en las ventanas. Solo usa la
biblioteca estándar.

`Dockerfile.capture` empaqueta únicamente los módulos del recolector, su schema y
`socket_sender.py`, además de los `__init__.py`. No necesita `application`,
`domain` ni dependencias ML. El paquete carga `AsyncSocketServer` de forma lazy
solo cuando se importa explícitamente, para que arrancar el recolector con `python
-m detection.infrastructure.tshark.stream_features` no cargue el agente.

## Container behavior

[`Dockerfile.capture`](../../Dockerfile.capture) packages only the capture
modules and schema. It does not need the application, domain, or ML
dependencies. The sidecar runs in Mosquitto's network namespace with
`NET_RAW` and `NET_ADMIN` capabilities.

Rebuild only the sidecar with:

```bash
docker compose up -d --build --force-recreate capture
```

By default all frames are captured. Use `--filter` to restrict the capture:

```bash
python -m detection.infrastructure.tshark.stream_features \
  --iface eth0 --filter mqtt --exclude-topic alertas/deteccion \
  --endpoint unix:///tmp/features.sock
```

Fields unavailable in a particular `tshark` version are sent as `null` with a
warning. The capture includes `ip.dst` and `tcp.stream` as connection context,
but those values are not model features.

## Flow context

The server runs one reader task per connection and routes frames to a worker
keyed by `(tenant_id, broker_id)`. Each worker keeps separate windows for
`(tcp.stream, ip.src, tcp.srcport, ip.dst, tcp.dstport)`, so responses from
different clients or reused ports are never mixed. Each direction has its own
window.

Per-flow mode skips records without complete source and destination endpoint
data. `FrameContext` correlates the client ID from CONNECT frames and the latest
topic by `tcp.stream`, and carries `tenant_id`, `broker_id` and `sensor_id`.
Subsequent frames inherit that context when their own fields are absent.

The evidence buffer uses `(tcp.stream, sorted endpoints)`, the same key as the
alert cooldown, so a piece of evidence includes both directions of one MQTT
connection. It keeps the last 30 seconds of raw records in memory and writes
them to `evidence/YYYY-MM-DD/<alert_id>.jsonl` when an alert is emitted.
