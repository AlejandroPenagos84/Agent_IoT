# `rules/` — Intrusion Rules

Reglas deterministas sobre `ConnectionEvent` del log del broker. Son **independientes
de los modelos** estadísticos: cubren señales que solo se ven a nivel de conexión
(por ejemplo, un CONNECT anónimo), no en los frames PUBLISH.

Implementan el *port* `core.protocols.IntrusionRule`
(`check(event) -> Alert | None`).

Patrón: **Strategy** + **Composite** (`AnyRule`).

## ¿Por qué existen (si ya hay modelos de ML)?

Los clasificadores de `classifiers/` ven **frames** (PUBLISH): tiempo, tamaño, puertos.
Pero hay ataques que **no son un frame visible**: el caso más claro es el ataque
`intrusion`, que es un **CONNECT anónimo** (conectar sin `username`). Un suscriptor
**nunca recibe el CONNECT** de otro cliente; ese evento solo aparece en el **log del
broker**.

Por eso las `rules` trabajan sobre los `ConnectionEvent` que produce `metadata/`, no
sobre frames. Cubren la capa de **conexión**, que el ML no puede oler.

## Analogía: el manual de seguridad

`metadata` es el **portero** que apunta quién entra. Las `rules` son el **manual de
seguridad** pegado en la pared:

- "Si entra alguien **sin identificación** → alarma." → `AnonymousConnectRule`.
- "Si alguien entra **5 veces en 10 segundos** → alarma." → `ConnectionChurnRule`.
- `AnyRule` = "ten todas las reglas en cuenta; si UNA salta, avisa".

## Flujo

```text
mosquitto.log ──▶ [metadata] ──ConnectionEvent──▶ [rules.check()]
                                                        │
                                            Alert(kind='intrusion')
                                                        │
                                            [AlertSink.emit()]
```

En el `Agent`, este flujo corre en un **hilo aparte** (`_consume_events`), en paralelo
al bucle de frames (`_consume_frames`). Ambos comparten el mismo `AlertSink`.

## Salida

Todas devuelven `core.types.Alert` con:

```json
{"ts": 1789563737.0, "kind": "intrusion", "label": "intrusion",
 "client_id": "atacante_intr", "ip": "192.168.20.42",
 "topic": null, "mse": null, "source": "broker-log"}
```

`source='broker-log'` distingue estas alertas de las que provienen del clasificador
(`source='plaintext'` o `'tls'`).


## `anon_connect.py` — `AnonymousConnectRule`

`AnonymousConnectRule(cooldown=5.0, source='broker-log')`

- Dispara cuando `event.anonymous` es `True` (CONNECT sin username).
- Devuelve `Alert(kind=ALERT_KIND_INTRUSION, label='intrusion', ...)`.
- `cooldown`: segundos mínimos entre alertas del mismo `client_id` (evita spam).
- `source`: etiqueta de origen incluida en la alerta.

## `churn.py` — `ConnectionChurnRule`

`ConnectionChurnRule(threshold=5, window=10.0, cooldown=5.0, source='broker-log')`

- Dispara si un `client_id` acumula `threshold` conexiones dentro de `window` segundos.
- Mantiene un `deque` de timestamps por cliente y descarta los antiguos.
- Aplica el mismo `cooldown` por cliente.

## `composite.py` — `AnyRule`

`AnyRule(rules: Sequence[IntrusionRule])`

- Patrón **Composite**: recorre las reglas y devuelve la **primera** `Alert` no nula.
- Si ninguna dispara, devuelve `None`.
- `factory.build_agent` lo construye por defecto como
  `AnyRule([AnonymousConnectRule(), ConnectionChurnRule()])`.

## `__init__.py`

Reexporta `AnonymousConnectRule`, `ConnectionChurnRule` y `AnyRule`.
