# `metadata/` — Broker Log Metadata (Adapter)

Deriva identidad de clientes y dueño de topics leyendo el **log de Mosquitto**.
Implementa el *port* `core.protocols.MetadataProvider`
(`get(client_id)` + `events()`).

¿Por qué el log? MQTT no lleva la IP/puerto del publicador en el mensaje, pero el
broker sí los conoce a nivel TCP y los escribe en su log. Leerlo es **observación del
broker** (fuente confiable), no una declaración del cliente.

Patrón: **Producer/Consumer** — un hilo hace *tail* del archivo y produce eventos en
una cola; `events()` los consume de forma segura entre hilos.

## ¿Qué problema resuelve?

Cuando un mensaje MQTT llega al agente, **el mensaje no dice quién lo publicó**: ni IP,
ni puerto, ni `client_id`. MQTT solo entrega `topic` + `payload`. Por tanto, sin ayuda
externa, el agente no podría rellenar `tcp.srcport` ni saber a qué cliente pertenece
cada frame.

El truco: el **broker sí conoce esa información** (la ve a nivel TCP) y la escribe en su
log. `BrokerLogRegistry` lee ese log y reconstruye la identidad que el protocolo MQTT
omite. Es **observación del broker** (fuente confiable), no una declaración del cliente
(un cliente podría mentir; el broker, no).

## Analogía: el portero

`metadata` es el **portero** del broker con una libreta. Anota:

- Quién entra: `quién → ip, puerto, ¿usuario?`.
- Quién habla en cada canal: `topic → quién`.

Cuando el agente recibe un frame, le pregunta al portero "¿de quién es este mensaje?" y
rellena `ip`/`srcport`. Cuando alguien entra sin identificarse, el portero lo apunta como
**anónimo** (y ahí entran las `rules`).

## Dos salidas (¡ojo, se usa para dos cosas!)

`BrokerLogRegistry` no solo produce eventos: también es una **tabla de consulta**. Sus
dos consumidores son:

| Salida | Método | Consumidor | Para qué |
|---|---|---|---|
| Identidad de un cliente | `get(client_id)` | `sources/` (vía `attributor`) | Rellenar `tcp.srcport` / `ip` de cada `FeatureRow`. |
| Dueño de un topic | `owner(topic)` / `attributor()` | `sources/` | Saber qué `client_id` publicó ese topic. |
| Eventos de conexión | `events()` | `Agent` → `rules/` | Detectar `intrusion` (CONNECT anónimo, churn). |

## Flujo completo

```text
Mosquitto ──escribe──▶ mosquitto.log
                            │
                 [BrokerLogRegistry]  (el portero)
                            │
              ┌─────────────┴──────────────────┐
              ▼                                 ▼
    get()/owner() ──▶ sources/        events() ──▶ rules.check()
    (rellena ip/srcport)             (ConnectionEvent)      │
              │                                              ▼
              ▼                                     Alert(kind='intrusion')
        FeatureRow ──▶ classifier ──▶ Alert ──▶ AlertSink
```

## Formatos de línea soportados (Mosquitto 2.x, `log_type all`)

```text
<epoch>: New connection from 172.18.0.2:54321 on port 1883.
<epoch>: New client connected from 172.18.0.2:54321 as temp_salon (p4, c1, k60, u'iot').
<epoch>: Received PUBLISH from temp_salon (d0, q0, r0, m0, 'home/salon/temperatura', ... (4 bytes))
<epoch>: Client temp_salon disconnected.
```

- La línea `New connection` aporta el `dstport` (el puerto del listener, 1883/8883),
  correlacionado con `New client connected` por `(ip, srcport)`.
- La ausencia de `u'...'` en `New client connected` ⇒ CONNECT **anónimo**.


## `broker_log.py`

### Regexes (formato de Mosquitto 2.x, `log_type all`)

| Regex | Línea que reconoce |
|---|---|
| `RE_CONNECTION` | `New connection from <ip>:<port> on port <dstport>.` |
| `RE_CONNECTED` | `New client connected from <ip>:<port> as <cid> (<flags>).` |
| `RE_DISCONNECTED` | `Client <cid> disconnected.` |
| `RE_PUBLISH` | `Received PUBLISH from <cid> (<flags> '<topic>', ... (<n> bytes))` |
| `RE_USERNAME` | Extrae `u'<username>'` de los flags (su ausencia ⇒ CONNECT anónimo). |

### Clase `BrokerLogRegistry`

| Método | Rol |
|---|---|
| `__init__(path, clock=None, from_start=False, poll=0.2)` | Configura el archivo y el intervalo de polling. `from_start=False` salta al final (no reproduce historia). |
| `start()` | Lanza el hilo daemon de *tail*. |
| `stop()` | Detiene el hilo (join con timeout de 2 s). |
| `get(client_id) -> ClientMeta \| None` | IP/puertos de un cliente (de la línea `New client connected`). |
| `owner(topic) -> str \| None` | Último `client_id` que publicó en ese topic (de `Received PUBLISH`). |
| `attributor() -> Callable` | Devuelve `lambda topic, payload: owner(topic)`, listo para inyectar en una `FeatureSource`. |
| `events() -> Iterator[ConnectionEvent]` | Consume la cola de conexiones (bloquea hasta que haya o se llame a `stop()`). |
| `_run()` | Bucle de lectura incremental: `seek(offset)`, `read()`, conserva **líneas parciales** y procesa las completas. |
| `_ingest(line)` | Actualiza `_pending`, `_clients`, `_queue` y `_owner`. |
| `_timestamp(line)` | Usa el epoch del prefijo (`<epoch>: ...`) o `clock.now()` si falla. |

### Estado interno

- `_clients`: `client_id → ClientMeta`.
- `_pending`: `(ip, srcport) → dstport` (se correlaciona con la línea `New connection`, que trae el puerto del listener).
- `_owner`: `topic → client_id`.
- `_queue`: `deque[ConnectionEvent]` compartida con `events()`.

### Limitaciones

- Depende del **formato exacto** de las líneas de Mosquitto; si cambia, los regex fallan.
- El timestamp del log tiene **resolución de segundos**; para `time_delta` fino, las
  fuentes usan su propio reloj de llegada.
- `owner(topic)` es "último publicador": en topics compartidos (p. ej. DoS sobre un topic
  normal) el dueño puede cambiar, lo cual es intencional para detección.
