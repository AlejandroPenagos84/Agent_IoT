# `sources/` — Feature Sources (Adapters)

Adaptadores que convierten **mensajes MQTT** en `FeatureRow` (las 7 features de red).
Implementan el *port* `core.protocols.FeatureSource`.

Patrón: **Strategy**. `PlaintextMqttSource` y `TlsMqttSource` son estrategias
intercambiables (misma interfaz, distinto listener/overhead). El agente no sabe cuál
usa; la elige `factory.build_source`.

Idea clave: el agente **emula el escenario cifrado**. Aunque un suscriptor reciba el
payload en claro, la decisión usa solo tamaño, tiempos y puertos — nunca el contenido
`mqtt.topic`/`mqtt.msg`. Así el modelo funciona igual con MQTTS.

## Fórmula de features

```
frame.time_relative        = now - t0                 (reloj de llegada al agente)
frame.time_delta           = now - t_anterior
frame.time_delta_displayed = frame.time_delta
frame.len = frame.cap_len  = mqtt_packet_size(topic, payload) + overhead
tcp.srcport                = puerto origen del cliente (resuelto vía metadata)
tcp.dstport                = puerto del listener (1883 / 8883)
```

`overhead` emula las cabeceras que MQTT no expone (`54` = Ethernet+IP+TCP para
plaintext; `83` = +29 de record TLS para la fuente TLS).

## `_features.py` — helpers puros

| Símbolo | Rol |
|---|---|
| `FIXED_HEADER = 2` | Cabecera fija MQTT (tipo + flags + longitud del remaining). |
| `TOPIC_LEN_PREFIX = 2` | Prefijo de longitud del topic. |
| `remaining_length(n)` | Tamaño de la codificación variable (`varint`) del remaining length. |
| `mqtt_packet_size(topic, payload)` | Estimación del tamaño real del paquete PUBLISH en bytes. |
| `build_row(time_relative, time_delta, frame_len, cap_len, srcport, dstport)` | Construye un `FeatureRow` con las 7 claves de `core.FEATURE_COLUMNS`. |

## `_stream.py` — `PahoMessageStream`

Encapsula paho + una `queue.Queue` thread-safe. Es **composición**, no herencia: las
fuentes crean y usan un stream, no heredan de él.

| Método | Rol |
|---|---|
| `start()` | `make_client(...)` (paho 1.x/2.x), registra callbacks, conecta y `loop_start()`. |
| `_on_connect` | Suscribe el cliente a todos los `topics` configurados. |
| `_on_message` | Encola `(topic, payload, ts)` con el **timestamp de llegada**. |
| `feed(topic, payload, ts=None)` | Inyecta un mensaje manualmente (tests, sin broker). |
| `messages()` | Generador que itera la cola con `timeout`; termina cuando `stop()` marca `_stopped`. |
| `stop()` | Marca parada, `loop_stop()` y `disconnect()`. Desbloquea `messages()`. |

## `plaintext_mqtt.py` — `PlaintextMqttSource`

Fuente sin TLS (listener `1883`). `DEFAULT_TOPICS = ('home/#', 'admin/#', 'cmd/#')`.

Constructor (parámetros clave):

| Parámetro | Default | Uso |
|---|---|---|
| `host`, `port` | `'localhost'`, `1883` | Broker. |
| `topics` | `DEFAULT_TOPICS` | Filtros de suscripción. |
| `client_id` | `'agente-1883'` | ID del suscriptor. |
| `metadata` | `None` | `MetadataProvider` para resolver IP/puerto. |
| `attributor` | `None` | `Callable[[topic, payload], client_id \| None]`. |
| `clock` | `None` | Reloj; si `None`, el agente inyecta `SystemClock`. |
| `overhead` | `54` | Bytes de cabecera añadidos a `frame.len`. |
| `attribute_retries`, `attribute_wait` | `5`, `0.05` | Reintentos para resolver el dueño del topic (ver abajo). |

Métodos: `start()`, `stop()`, `rows() -> Iterator[FeatureRow]` y privados
`_client_id(topic, payload)` / `_context(topic, payload)`.

**Atribución y race condition:** MQTT **no** incluye el `client_id` del publicador en el
PUBLISH. El `attributor` lo deduce del log del broker (`owner(topic)`), que llega de
forma asíncrona. Para evitar `srcport = 0` en los primeros mensajes, `_client_id`
reintenta hasta `attribute_retries` veces cada `attribute_wait` segundos.

`last_context` expone el contexto del último mensaje (`client_id`, `ip`, `topic`,
`srcport`, `dstport`) para que el agente enriquezca las `Alert`.

## `tls_mqtt.py` — `TlsMqttSource`

Igual que la anterior pero con `tls_set` sobre el listener `8883`.

| Símbolo | Valor | Rol |
|---|---|---|
| `TLS_RECORD_OVERHEAD` | `29` | Record TLS: header (5) + nonce (8) + tag (16). |
| `TCP_IP_ETH_OVERHEAD` | `54` | Cabeceras Ethernet+IP+TCP. |
| `DEFAULT_OVERHEAD` | `83` | Suma aplicada por defecto a `frame.len`. |

Parámetros TLS: `ca_certs`, `certfile`, `keyfile`, `insecure` (`cert_reqs = 0`, solo dev).
