# `mosquitto/` — Broker Configuration

Configuración del broker MQTT usado por `docker-compose.yml`. No es código Python.

## `config/mosquitto.conf`

| Directiva | Valor | Por qué |
|---|---|---|
| `persistence false` | — | No se guardan sesiones entre reinicios (simulación efímera). |
| `allow_anonymous true` | — | Permite CONNECT sin credenciales; es lo que usa el ataque `intrusion` del simulador. |
| `log_dest file /mosquitto/log/mosquitto.log` | — | Log en el volumen compartido (debug). |
| `log_dest stdout` | — | Log también a la salida del contenedor. |
| `log_type all` | — | Registra conexiones y publicaciones. |
| `log_timestamp true` | — | Añade marca temporal a cada línea. |
| `listener 1883` | claro | Tráfico MQTT sin cifrar. |
| `listener 8883` | TLS | Tráfico MQTTS (`certfile`/`keyfile`). |
| `max_queued_messages 0` / `message_size_limit 0` | — | Sin límites (el simulador usa payloads de varios tamaños). |

El log vive en un **volumen compartido** (`mosquitto-log`). En el refactor actual el
agente **no** lo consume (la atribución de `client_id` vía log quedó pendiente); sirve
para depurar el broker.

## Certificados (servicio `certgen`)

El servicio `certgen` del compose genera `certs/server.crt`, `certs/server.key` y
`certs/ca.crt` con OpenSSL (autofirmados, SAN `DNS:mosquitto,DNS:localhost,IP:127.0.0.1`)
y prepara `mosquitto/log` con permisos de escritura.

`mosquitto` **no** usa `depends_on: certgen` porque `podman-compose` traduce cualquier
`depends_on` a `podman --requires`, y podman rechaza arrancar un contenedor que depende
de otro ya terminado (`container state improper`). En su lugar, el `command` de
`mosquitto` espera a que existan los certificados (hasta 60 s) antes de `exec` el broker.

`certs/` y `log/` están en `.gitignore` y `.dockerignore`: son artefactos de runtime.
