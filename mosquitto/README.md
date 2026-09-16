# `mosquitto/` — Broker Configuration

Configuración del broker MQTT usado por el `docker-compose.yml`. No es código Python.

## `config/mosquitto.conf`

| Directiva | Valor | Por qué |
|---|---|---|
| `persistence false` | — | No se guardan sesiones entre reinicios (simulación efímera). |
| `allow_anonymous true` | — | Permite CONNECT sin credenciales; es lo que dispara la regla de `intrusion`. |
| `log_dest file /mosquitto/log/mosquitto.log` | — | El agente hace *tail* de este archivo (`metadata.BrokerLogRegistry`). |
| `log_dest stdout` | — | Log también a la salida del contenedor. |
| `log_type all` | — | Necesario para que aparezcan `New client connected` y `Received PUBLISH`. |
| `listener 1883` | claro | Tráfico MQTT sin cifrar. |
| `listener 8883` | TLS | Tráfico MQTTS (`certfile`/`keyfile`). |

El log vive en un **volumen compartido** (`mosquitto-log`) entre `mosquitto` y `agente`.

## Certificados (servicio `certgen`)

El servicio `certgen` del compose genera `certs/server.crt`, `certs/server.key` y
`certs/ca.crt` con OpenSSL (autofirmados, SAN `DNS:mosquitto,DNS:localhost,IP:127.0.0.1`)
y prepara `mosquitto/log` con permisos de escritura. `mosquitto` arranca solo cuando
`certgen` termina (`service_completed_successfully`).

`certs/` y `log/` están en `.gitignore` y `.dockerignore`: son artefactos de runtime.
