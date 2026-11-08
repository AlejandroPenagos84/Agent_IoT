# Plan — Captura por streaming (socket Unix) en lugar de `features.jsonl`

## Problema

Hoy la captura escribe todos los frames en un único `/capture/features.jsonl`
que crece sin límite y nunca se limpia. Con tráfico real llena el disco.

Además:

- **Guarda datos sensibles.** `CAPTURE_FIELDS` incluye `mqtt.passwd`,
  `mqtt.username` y `mqtt.msg` (el payload completo). Con MQTT sin TLS, las
  contraseñas de los dispositivos quedan en texto plano en el disco.
- **No se puede rotar desde fuera.** `stream_features.py` abre el archivo una sola
  vez (`open(args.out, 'a')`). Con `logrotate` en modo `create`, tshark sigue
  escribiendo en el archivo renombrado; con `copytruncate` se pierden líneas.
- **El agente lee un archivo que nadie necesita conservar.** Solo lo sigue
  (`TsharkFeatureSource`) y al reiniciar salta al final, así que lo escrito
  mientras estaba caído tampoco se procesa.

## Objetivo

1. Escribir solo los campos que usa el modelo TCP y el contexto de las alertas.
2. Pasar los registros de la captura al agente **en streaming**, sin escribir
   frames en disco.
3. No bloquear nunca a tshark: si el agente no está o va lento, descartar
   registros y contarlos.
4. Guardar como evidencia los frames alrededor de cada alerta, con su propia
   retención.

## Decisiones

| Decisión | Valor | Motivo |
|---|---|---|
| Modelos soportados | Solo `tcp` | Se eliminan `lstm`, `hybrid`, `xgboost` y `tls` (fase 0). |
| Transporte | Socket Unix `SOCK_STREAM` en el volumen compartido | Los dos contenedores están en el mismo host pero en distintas redes; un socket en un volumen los conecta sin abrir puertos. |
| Quién escucha | El agente (servidor) | La captura reintenta la conexión; el orden de arranque deja de importar. |
| Formato | JSON por línea (NDJSON), UTF-8 | Es el formato de hoy; el parser actual se reutiliza. |
| Cola en la captura | `deque(maxlen=50_000)` | Absorbe picos y reinicios cortos del agente. Si se llena, se descartan los más viejos. |
| Reintento de conexión | Cada 1 s | Reinicios del agente se recuperan rápido. |
| Pérdida aceptada | Registros mientras el agente está caído o la cola está llena | Mismo criterio que un IDS en tiempo real. Se registra cuántos. |
| Evidencia por alerta | 30 s del flujo, ambas direcciones del `tcp.stream`, en memoria del agente | Para revisar un DoS hay que ver qué respondió el broker (CONNACK, cierre de conexión); eso viaja en la dirección contraria. No depende de guardar los frames en disco. |
| Clave del búfer de evidencia | `(stream_id, endpoints ordenados)` | Es la misma `_connection_key` del cooldown, así evidencia y supresión agrupan igual. |
| Ruta de evidencia | `evidence/YYYY-MM-DD/<alert_id>.jsonl` | Fecha UTC del momento de escritura. Se lee fácil a mano y permite retención por carpeta sin abrir archivos. |
| Retención de evidencia | 30 días, por carpeta de fecha | La limpia el ETL borrando carpetas completas. No usa `mtime` ni el reloj de captura. |
| Lectura de archivo | Sin alternativa | La captura y el agente se despliegan juntos con el mismo Compose. Mantener el modo archivo reintroduce el archivo que crece sin límite que este plan elimina; el código viejo queda en git. |
| Dependencias del sidecar | Solo biblioteca estándar | Igual que hoy (`Dockerfile.capture`). |

Alternativas descartadas:

- **Segmentos en disco con checkpoint.** Permiten reprocesar tráfico pasado,
  pero añaden rotación, archivos `.open`, checkpoints y casos de segmentos
  borrados mientras se leen. Para detección en tiempo real no compensa.
- **Redis Streams.** El sidecar dependería de Redis y, si Redis se cae, la
  captura se detiene.
- **tshark dentro del contenedor del agente.** Daría `NET_RAW` y la red del
  broker a la imagen grande con XGBoost y pandas. El sidecar con permisos
  especiales debe seguir siendo mínimo.
- **Mantener `TsharkFeatureSource` como modo alternativo.** Vuelve a crear un
  archivo que crece sin límite y duplica caminos de datos que ya no se usan.
- **Guardar todo el tráfico de una IP.** La evidencia incluiría varias
  conexiones y crecería mucho más. Se puede añadir después si hace falta.

## Diseño

```text
tshark ─► stream_features ─► cola acotada ─► hilo emisor ─► /capture/features.sock
          (TcpWindowFeatures)                (reconecta)             │
                                                                      ▼
                                         AsyncSocketServer (asyncio, N conexiones)
                                                                      │
                                   BrokerPool: 1 worker por (tenant, broker)
                                                                      │
                                              Agent ─► AlertSink / EvidenceSink
```

- `TcpWindowFeatures` sigue en la captura. Así las ventanas de 5 s y el conteo de
  conexiones nuevas se mantienen correctos aunque el agente se reinicie.
- La captura nunca espera al agente: el hilo principal solo hace `append` a la
  cola; el hilo emisor es el único que toca el socket.
- El agente acepta muchas conexiones concurrentes con asyncio. Cada conexión
  tiene su propio lector y parser; todas enrutan a un worker por broker.
- Cada worker tiene su propia cola acotada y su propio `Agent`. La cola llena
  aplica backpressure solo a las conexiones de ese broker.
- El pool está limitado a 256 workers y evicta workers inactivos a los 10 min.
- El socket vive en `capture-data`, que ya montan los dos contenedores. Ambos
  deben estar en el mismo host; un socket Unix no funciona sobre NFS ni EFS.

## Fases

Cada fase es un commit con sus tests. Correr la suite completa después de cada una:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

### Fase 0 — Eliminar los modelos MQTT antiguos

Borrar:

- `src/detection/infrastructure/classifiers/{anomaly,hybrid,xgb,tls}.py`.
- `src/detection/infrastructure/classifiers/_frame.py` (solo lo usan los
  clasificadores MQTT/TLS que se eliminan).
- De `_common.py`: `build_mqtt_features`, `build_case1`, `build_lstm_raw`,
  `crear_secuencias`, `recon_mse`, `entropia`, `build_network_features`,
  `select_features` y las constantes que solo usen ellos (`COLS_RED`,
  `MQTT_NUMERIC_COLUMNS`, `MODEL_FEATURES`, `SEQ_LEN`, `NAN_FILL`). Conservar
  `load_config` y `validate_named_features`, que usa `TcpXgbClassifier`.
- `modelos_agente/` (artefactos MQTT).
- En `composition_root.py`: el diccionario de clasificadores, la validación
  `feature_mode == 'mqtt'` y las ramas `if tcp`. `AgentConfig.model` desaparece
  o solo acepta `tcp`.
- En `docker-compose.yml`: la variable `MODELO`, el volumen
  `./modelos_agente` y la expresión que elige `model_dir`.
- `torch` de `requirements.txt` y el comentario sobre el build CPU
  (`requirements.txt:3-4`).
- Tests y validaciones que dependen de lo anterior:
  `tests/test_agent_windows.py` (quitar el import y el test de
  `crear_secuencias`, y las partes de features MQTT; conservar los tests de
  ventanas por flujo), `tests/validate_notebook.py` (valida el notebook antiguo).
- Documentación: README principal (secciones "Choosing and running the
  detector", referencias a `modelos_agente/` en las líneas 74 y 440 y las
  opciones `MODELO`), `src/detection/infrastructure/classifiers/README.md`.

Revisar antes con:

```bash
grep -rnE "AnomalyClassifier|HybridClassifier|XgbClassifier|TlsClassifier|build_mqtt_features|crear_secuencias|recon_mse|modelos_agente[^_]|torch|lstm" \
  --include=*.py --include=*.yml --include=*.md --include=*.txt --include='Dockerfile*' . \
  | grep -v "^./ML_Model/\|^./plans/"
```

`ML_Model/backup/` se conserva como historia del proyecto.

Mantener el campo `mse` de `Alert` y del ETL: es opcional y no rompe nada. Se
puede quitar en una limpieza aparte.

**Criterio:** la imagen principal ya no instala `torch`, `build_agent` solo crea
`TcpXgbClassifier` y la suite pasa.

### Fase 1 — Enviar solo los campos necesarios

En `tshark_schema.py`, reemplazar `CAPTURE_FIELDS` por dos listas:

- **Campos que pide tshark** (`-e`), los mínimos para calcular las features y el
  contexto:
  `frame.time_epoch`, `frame.time_delta`, `frame.len`, `ip.src`, `ip.dst`,
  `tcp.srcport`, `tcp.dstport`, `tcp.stream`, `mqtt.msgtype` (lo usa
  `TcpWindowFeatures` para separar sesiones en cada CONNECT), `mqtt.clientid` y
  `mqtt.topic` (contexto de la alerta y exclusión del publicador de alertas).
- **Campos del registro enviado:** los anteriores, menos `mqtt.msgtype`, más
  `tcp_features`.

Nunca se piden ni se envían `mqtt.passwd`, `mqtt.username`, `mqtt.msg` ni los
campos `will*`.

Cambios:

- `stream_features.py`: usar la lista nueva en `build_command` y en
  `record_from_fields`. Quitar la decodificación especial de `mqtt.msg`.
- No enviar registros con `tcp_features` en `null` (frames fuera de 1883/8883):
  el agente los descarta de todas formas.
- `tshark_feature_source.py`: con solo el modelo TCP, `feature_key` deja de ser
  opcional; quitar `NETWORK_COLUMNS` y la rama de features crudas.
- `FEATURE_COLUMNS` de `tshark_schema.py` ya no se usa si se borró `_frame.py` en
  la fase 0; eliminarlo.

Esta fase todavía escribe en `features.jsonl`; el transporte cambia en la fase 2.
`Dockerfile.capture` sigue con `--out` hasta la fase 2.

Tests:

- Un registro no contiene ninguna clave `mqtt.passwd`, `mqtt.username` ni
  `mqtt.msg`.
- `build_command` solo incluye los campos de la lista mínima.
- Reescribir `tests/test_mqtt_capture.py`: eliminar la comparación de `FIELDS`
  con el header de `dataset/DoS.csv` y las pruebas de decodificación de
  `mqtt.msg`; conservar `build_command`, `build_display_filter` y añadir las
  comprobaciones de la lista mínima.
- `tests/test_tcp_agent.py` sigue pasando.

### Fase 2 — Emisor por socket en la captura

Nuevo módulo `src/detection/infrastructure/tshark/socket_sender.py` (solo
biblioteca estándar), usado por `stream_features.py`:

```python
class SocketSender:
    def __init__(self, path: str, queue_size: int = 50_000,
                 retry_seconds: float = 1.0, stats_seconds: float = 60.0): ...
    def start(self) -> None: ...        # arranca el hilo emisor (daemon)
    def send(self, line: str) -> None: ...  # no bloquea; descarta si la cola está llena
    def close(self, timeout: float = 2.0) -> None: ...
    @property
    def stats(self) -> dict: ...        # enviados, descartados, reconexiones
```

Reglas:

1. `send` solo hace `append` a un `deque(maxlen=queue_size)` protegido por un
   `threading.Lock` (o `Condition` para despertar al hilo). Antes del `append`,
   si `len(queue) == queue_size`, contar un descarte: el `deque(maxlen=...)`
   expulsa el más viejo sin avisar.
2. El hilo emisor:
   - Si no hay conexión, intenta `socket.connect(path)`. Si falla
     (`FileNotFoundError`, `ConnectionRefusedError`), espera `retry_seconds` y
     reintenta. Mientras tanto la cola sigue llenándose y descartando lo viejo.
   - Con conexión, saca un lote de la cola (por ejemplo hasta 500 líneas), las
     une y hace `sendall`. Cada línea termina en `\n`.
   - Si `sendall` falla (`BrokenPipeError`, `ConnectionResetError`), cierra el
     socket, cuenta el lote como descartado y vuelve a reconectar. No reenviar el
     lote: el agente pudo haber recibido una parte y se duplicarían frames.
3. Cada `stats_seconds`, imprimir a stderr una línea JSON con enviados,
   descartados y reconexiones desde el último reporte. Si hubo descartes, que el
   mensaje lo diga claramente.
4. Al terminar (`SIGTERM`, fin de tshark), `close` despierta al hilo emisor e
   intenta vaciar la cola durante `timeout` segundos y luego sale. No debe
   esperar el timeout completo si no hay servidor.
5. Mantener la exclusión actual del publicador de alertas
   (`--exclude-client-id`, `--exclude-topic`) antes de `send`.

Flags nuevos en `parse_args`:

- `--socket` (por defecto `/capture/features.sock`). Reemplaza `--out`.
- `--queue-size` (50000), `--retry-seconds` (1.0).

Eliminar `--out` y la escritura a `features.jsonl`. Si se necesita depurar, usar
un cliente de prueba que escuche en el socket (ver tests).

Compose y Dockerfile:

- El `command` de `capture` pasa de `--out /capture/features.jsonl` a
  `--socket /capture/features.sock`.
- `Dockerfile.capture` debe copiar `socket_sender.py` en el `COPY` explícito y
  cambiar su `CMD` a `--socket /capture/features.sock`.

Tests (con un directorio temporal y un servidor de prueba en un hilo):

- Sin servidor, `send` no bloquea; con `queue_size=10` y 100 envíos, quedan 10 en
  cola y 90 descartados.
- Al levantar el servidor, recibe las líneas en orden y completas.
- Si el servidor se cae y vuelve, el emisor reconecta y sigue enviando.
- `close` vacía la cola si el servidor está disponible.

### Fase 3 — Fuente por socket en el agente

> Nota: la implementación final reemplazó `SocketFeatureSource` por
> `AsyncSocketServer` (asyncio, muchas conexiones) + `BrokerPool` (un worker por
> `(tenant, broker)`). El `SocketFeatureSource` descrito abajo quedó como diseño
> intermedio.

Nuevo `SocketFeatureSource` en `src/detection/infrastructure/tshark/`, que
reemplaza a `TsharkFeatureSource`. Mantiene la interfaz `FeatureSource`
(`start`, `rows`, `stop`), así que `Agent` no cambia.

```python
class SocketFeatureSource(FeatureSource):
    def __init__(self, path: str = '/capture/features.sock',
                 accept_timeout: float = 1.0,
                 max_line_bytes: int = 64 * 1024): ...
```

Antes de borrar `tshark_feature_source.py`, mover su parser a
`src/detection/infrastructure/tshark/record_parser.py`:

- `features(record) -> FeatureRow | None`: devuelve solo `tcp_features`.
- `context(record, client_ids, last_topics) -> FrameContext` y `resolve_flow`.
- `_remember` con el límite `MAX_TRACKED_FLOWS`.

Después borrar `tshark_feature_source.py` y toda la lectura de archivo. Nadie
más lo usa y el modo archivo reintroduce el problema de disco que este plan
elimina; el código viejo queda en el historial de git.

Reglas:

1. **`start`.** Si existe un archivo en `path` (socket viejo de una ejecución
   anterior), borrarlo con `os.unlink`. Crear el socket, `bind`, `chmod 0o660` y
   `listen(1)`. Usar `settimeout(accept_timeout)` para que `stop()` funcione.
2. **`rows`.** Mientras no se pida parar:
   - Esperar conexiones con `select`/`poll` sobre el socket de escucha y la
     conexión abierta, o usar timeout también en `recv`. Así se detecta una
     captura reiniciada aunque la conexión anterior siga abierta, y una conexión
     colgada no bloquea `stop()`.
   - Si llega una conexión nueva mientras hay otra abierta, cerrar la anterior
     y usar la nueva.
   - Leer con `recv` en bloques, juntar en un búfer y separar por `\n`. La parte
     sin `\n` final queda para el siguiente bloque.
   - Si una línea supera `max_line_bytes` sin `\n`, descartarla (protege la
     memoria si llega basura).
   - Decodificar cada línea como JSON; ignorar las que fallen.
   - Convertir cada registro en `Frame` con el parser compartido (`record_parser`),
     conservando el registro crudo en el `Frame` para la evidencia de la fase 4.
   - Si la conexión se cierra, vaciar el búfer parcial y volver a esperar.
3. **`stop`.** Marcar la parada, cerrar la conexión y el socket de escucha y
   borrar el archivo del socket.
4. **Caché de contexto.** `_client_ids` y `_last_topics` se conservan entre
   reconexiones de la captura, porque los `tcp.stream` siguen vivos. Se pierden
   si el agente se reinicia, igual que hoy.

Cambios en `composition_root.py` y `AgentConfig`: reemplazar `capture_path`,
`capture_from_start` y `capture_poll` por `capture_socket`. Actualizar el
`command` de `agente` en Compose. El volumen `capture-data` del agente deja de ser
`:ro`, porque el agente crea el socket.

Actualizar además `tshark/__init__.py` (exportar `SocketFeatureSource` en lugar
de `TsharkFeatureSource`) y `src/detection/infrastructure/classifiers/README.md`.

Documentación: actualizar el diagrama y la sección de Compose del README
(`features.jsonl` → `features.sock`) y el comando de ejecución local.

Tests (con un directorio temporal):

- Un cliente que envía líneas parciales y completas produce los `Frame`
  esperados, en orden.
- Las líneas que no son JSON se ignoran y las siguientes se procesan.
- Si el cliente se desconecta y otro se conecta, la fuente sigue entregando
  frames sin reiniciarse.
- Una captura que se queda colgada no impide que `stop()` termine.
- `stop()` termina `rows()` en menos de `accept_timeout` y borra el archivo del
  socket.
- Prueba de punta a punta: `SocketSender` (fase 2) → `SocketFeatureSource` →
  `Agent` con un clasificador falso emite la alerta esperada.
- Adaptar `tests/test_tcp_agent.py` y los tests de parser de
  `tests/test_agent_windows.py` al parser compartido o a `SocketFeatureSource`.

### Fase 4 — Evidencia por alerta

Camino de datos:

- Añadir `record: dict | None = None` a `Frame`
  (`application/ports/types.py`). `SocketFeatureSource` rellena el JSON
  decodificado; así el agente tiene el frame crudo sin volver a parsear ni
  escribir archivos.
- En el agente, mantener `dict[key, deque]` con `(frame.time_epoch, record)` por
  conexión, usando **la misma `_connection_key` del cooldown**
  (`(stream_id, endpoints ordenados)`). Así la evidencia incluye ambas
  direcciones del mismo `tcp.stream` y el cooldown agrupa igual.
- Descartar por tiempo de captura (`evidence_seconds = 30`) y también limitar el
  `deque` con `maxlen` para acotar ráfagas con timestamps casi iguales. Limitar
  el número de flujos en memoria igual que `MAX_TRACKED_FLOWS`.

Puerto nuevo en `application/ports`:

```python
class EvidenceSink(ABC):
    def write(self, alert: Alert, key, records: Sequence[dict]) -> None: ...
```

Adaptador de archivo en `infrastructure/sinks`:

1. Escribir `evidence/YYYY-MM-DD/<alert_id>.jsonl`, con la fecha UTC **del
   momento de escritura** (`datetime.now(timezone.utc)`), no `mtime` ni el
   reloj de captura.
2. Primera línea con la alerta (incluye `alert_id` y `ts`); después un registro
   crudo por línea. El `ts` de la alerta queda dentro del archivo para analizarlo
   después.
3. Usar un archivo `.tmp` y `os.replace`.
4. Respetar el cooldown actual: una sola evidencia por alerta emitida.
5. Si el directorio de evidencia supera un tope (por ejemplo 500 MB), no escribir
   más y registrar un `WARNING`. Las alertas siguen saliendo.

Inyectar `EvidenceSink` en `Agent` desde el composition root, para que `Agent`
no escriba archivos directamente y más adelante se pueda cambiar el destino
(S3, MinIO).

Hoy el agente no genera `alert_id`: `Alert` no tiene ese campo y el ETL lo calcula
después con `_stable_alert_id`, a partir del contenido de la alerta. Agregar
`alert_id` (UUID) a `Alert`, generarlo en el agente y escribirlo en la alerta. El
ETL ya respeta un `alert_id` recibido (`alert_id_origin = 'provided'`), así que
alerta, evidencia y datos normalizados comparten el mismo id. Actualizar
`tests/test_alert_sinks.py` por el campo nuevo en `to_dict`.

La evidencia se guarda en un volumen propio (`evidence-data:/evidence`) para que
no dependa de `capture-data`.

Tests:

- Una alerta crea un archivo de evidencia con los registros de la conexión de los
  últimos 30 s, incluyendo ambas direcciones del `tcp.stream` y ninguno de otros
  flujos.
- Con cooldown activo, no se crean evidencias duplicadas.
- Al superar el tope, no se escribe evidencia y la alerta igual se emite.
- La ruta usa la fecha UTC de escritura y la primera línea contiene el
  `alert_id` y el `ts` de la alerta.

### Fase 5 — Retención de evidencia y alertas en el ETL

Agregar al ciclo del servicio `etl` un paso de limpieza:

- Borrar carpetas `evidence/YYYY-MM-DD/` cuya fecha sea anterior a
  `hoy_utc - EVIDENCE_RETENTION_DAYS` (por defecto 30). Borrar la carpeta
  completa, sin abrir archivos ni usar `mtime`. Ignorar nombres que no parseen.
- Opcional: borrar alertas diarias `/alerts/YYYY-MM-DD.jsonl` con más de N días
  (`ALERT_RETENTION_DAYS`, desactivado por defecto), solo después de que el ETL
  las haya normalizado.

El servicio `etl` debe montar `evidence-data`.

Tests con carpetas y nombres de fecha concretos (sin `os.utime`).

## Lo que este plan no incluye

- Muestras para reentrenar. Si hacen falta, la captura puede escribir una
  fracción de los registros (`--sample-rate`) en `samples/` con su propia
  retención, sin tocar el flujo en tiempo real.
- Evidencia de todo el tráfico de una IP. La evidencia se limita a la conexión
  (`tcp.stream`); agrupar por IP haría los archivos mucho más grandes.
- Enviar evidencia o alertas fuera de la máquina (S3, MinIO, SIEM).
- Logging estructurado del agente. Conviene hacerlo antes o junto con la fase 3,
  para registrar conexiones, desconexiones y líneas descartadas.

## Criterios de aceptación

- La captura no escribe frames en disco; `features.jsonl` desaparece del código,
  de Compose y del README. Tampoco queda `TsharkFeatureSource` ni modo archivo.
- Ningún registro enviado contiene `mqtt.passwd`, `mqtt.username` ni `mqtt.msg`.
- Con el agente detenido, la captura sigue corriendo, no bloquea a tshark y
  reporta cuántos registros descartó.
- Al volver el agente, la captura reconecta sola en pocos segundos y el agente
  vuelve a emitir alertas sin reiniciar la captura.
- Reiniciar la captura no obliga a reiniciar el agente; una captura colgada no
  bloquea `stop()`.
- Cada alerta emitida tiene su evidencia, salvo que se haya superado el tope.
- La evidencia contiene ambas direcciones del mismo `tcp.stream` y ningún frame
  de otra conexión.
- La retención borra carpetas completas por fecha UTC de escritura y no depende
  de `mtime` ni del reloj de captura.
- `docker compose up` funciona con los flags nuevos y la suite pasa.
