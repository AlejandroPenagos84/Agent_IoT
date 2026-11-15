# Captura (sidecar del cliente)

La captura corre `tshark`, convierte los campos seleccionados, calcula las
features TCP y envía un registro NDJSON por frame al agente por un socket Unix o
TLS. Nunca escribe frames a disco. Solo usa la biblioteca estándar.

Se ejecuta con `python -m capture` (`composition_root.main`).

## Capas

| Capa | Contenido |
|---|---|
| `domain/` | Reglas puras: features TCP (`TcpWindowFeatures`), `SensorState` (identidad y regla de media vida del token), `ClientStreamExclusion` y `wire_record`. |
| `application/ports/` | `PacketSource`, `RecordSender`, `EnrollmentApi`, `SensorStateStore`. |
| `application/use_cases/` | `EnrollSensor`, `RefreshSensorToken`, `StreamFeatures`. |
| `infrastructure/tshark/` | `TsharkPacketSource` (implementa `PacketSource`), `build_command`, `parse_line`/`record_from_fields` y `CAPTURE_FIELDS`. |
| `infrastructure/enrollment/` | `ApiClient` (`EnrollmentApi`), `FileSensorStateStore` (`SensorStateStore`) y `SensorCredentials`. |
| `infrastructure/transport/` | `SocketSender` (`RecordSender`) y sus piezas. |
| `cli.py` | `parse_args`: flags y variables de entorno. |
| `composition_root.py` | Arma adaptadores y casos de uso: inscribe, arranca tshark y corre `StreamFeatures`. |

Casos de uso:

- `EnrollSensor.execute(key, name)`: reutiliza la identidad guardada si la clave
  no cambió (validándola con un refresh) o inscribe con `POST /sensors/enroll`.
  Si la instalación fue revocada y la clave es la misma, lanza `EnrollmentError`
  en vez de re-inscribir.
- `RefreshSensorToken.execute(state)`: heartbeat; adopta el token nuevo cuando el
  actual pasó la mitad de su vida. Un rechazo marca el estado como revocado.
- `StreamFeatures.execute()`: lee registros de la fuente, excluye el stream del
  publisher de alertas, calcula las features y envía cada línea NDJSON.

`SensorCredentials` es la fachada de infraestructura de la inscripción (como
`SocketSender` para el transporte): compone los dos primeros casos de uso y
aporta los reintentos de red con backoff y el hilo del heartbeat.

## Transporte

`infrastructure/transport/` contiene `SocketSender`, dueño del socket del lado de la
captura. `send` solo agrega a una cola acotada; un hilo propio conecta, reconecta,
envía por lotes y reporta cuántos registros se enviaron, descartaron o requirieron
reconexión. Endpoints: `unix:///ruta` (desarrollo) o `tls://host:puerto`
(producción). Con token envía `{"type":"hello","token":"<sensor-jwt>"}` en cada
conexión y espera `{"type":"hello_ack"}` antes de mandar features.

| Archivo | Contenido |
|---|---|
| `socket_sender.py` | `SocketSender`: hilo de envío, lotes, reconexión y cierre con vaciado. `SocketSender.from_endpoint(...)` lo arma desde la configuración. |
| `connector.py` | Protocolo `Connector` y `connector_for(endpoint, ...)`, que elige el adaptador. |
| `unix_connector.py`, `tls_connector.py` | Abren el socket Unix o TCP+TLS. |
| `token_auth.py` | `TokenAuth`: token fijo o renovado por la inscripción, pausa si está revocado y handshake `hello`/`hello_ack`. |
| `drop_oldest_queue.py` | `DropOldestQueue`: cola acotada que descarta el registro más viejo. |
| `sender_stats.py` | `SenderStats`: contadores y reporte periódico por stderr. |

Del lado del agente, `detection/infrastructure/transport/` recibe estas conexiones.
`AsyncSocketServer` solo maneja el hilo con el event loop, `start`/`stop` y la
aceptación; el resto lo delega:

| Archivo | Contenido |
|---|---|
| `listener.py` | Protocolo `Listener` y `listener_for(endpoint, ssl_context)`. |
| `unix_listener.py`, `tls_listener.py` | Abren el socket Unix (0660) o TCP+TLS (expone `port`). |
| `connection_limiter.py` | `ConnectionLimiter`: tope de conexiones, `rejected` y cancelación al cerrar. |
| `sensor_auth.py` | `SensorAuth`: handshake `hello`/`hello_ack` y validación del token. |
| `sensor_identity.py` | `SensorIdentity`: ids del token, `bind` (antisuplantación) y vencimiento. |
| `sensor_connection.py` | `SensorConnection`: una conexión de punta a punta (auth, lectura NDJSON con plazo del token, `RecordParser` y `route`). |
| `server_tls.py` | `server_ssl_context(...)` y `CertificateReloader` (recarga el certificado al renovarse). |

`broker_pool.py` (application layer) creates one `Agent` worker per
`(tenant_id, broker_id)`, with its own bounded queue and classifier. A full
queue applies backpressure only to that broker's connections. Idle workers are
evicted after 10 minutes; the pool is capped at 256 workers.

`record_parser.py` (`RecordParser`) contains the parser shared by the source and
tests: it reads `tcp_features`, resolves the alert context and caches client ID
and topic per `tcp.stream`.

`infrastructure/tshark/schema.py` defines the tshark fields (`CAPTURE_FIELDS`); the safe
record sent to the agent (`RECORD_FIELDS`) comes from `wire.protocol`. Passwords, usernames, payloads and
will fields are never requested.

`tcp_window_features.py` (`TcpWindowFeatures`) calcula en línea las 12 features TCP
del modelo B y el caso de uso `StreamFeatures` las envía en cada registro como
`tcp_features` (dict en el orden de `TCP_FEATURE_COLUMNS`). Es el espejo incremental
de `ML_Model/data_preprocessing/tcp_features.py`: mismas ventanas causales de 5 s y
mismas claves de conexión (endpoints + nº de CONNECT) y dirección.
`tests/test_tcp_window_features.py` comprueba que coincide exactamente con la matriz
de entrenamiento sobre `DoS.csv`. Como el modelo se entrenó con la vista `mqtt`,
los frames sin puerto 1883/8883 no se envían ni entran en las ventanas. Solo usa la
biblioteca estándar.

El dominio está en `domain/`:

| Archivo | Contenido |
|---|---|
| `frame.py` | `TcpFrame`: valida el registro de tshark (IP, puertos, tiempo, alcance MQTT) y da las claves de conexión y dirección. |
| `windows.py` | `RollingStats` (conteo, suma, desviación de los valores previos) y `EventCounter`, ventanas causales de 5 s. |
| `lru.py` | `LruDict`: estado por flujo acotado, expulsa la clave usada hace más tiempo. |
| `tcp_window_features.py` | `TcpWindowFeatures`: une las piezas y arma el vector de 12 features. |

`Dockerfile.capture` empaqueta solo `src/capture` y `src/wire` (el contrato
compartido). No incluye el agente ni dependencias ML.

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
python -m capture \
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
