# 05 — Alta de brokers e inscripción automática de la captura

## Objetivo

El cliente registra su broker desde la web y pega un solo comando en su
servidor (nube o local). Sin editar `.env`, sin crear sensores ni emitir tokens
a mano.

## Decisiones

| Tema | Decisión |
|---|---|
| Clave de inscripción | Una por broker. La devuelve el endpoint existente `POST /api/v1/brokers`. |
| Capturas por broker | Una. El broker tiene como máximo un sensor. |
| Reinstalación | Se vuelve a inscribir con la misma clave: reemplaza las credenciales del sensor y la instalación anterior queda fuera. |
| Clave perdida o filtrada | `POST /api/v1/brokers/{id}/enrollment-key` la rota; la anterior deja de servir. |
| Red del cliente | Solo salida: `:443` (API) y `:8443` (agente). Sin puertos de entrada. |
| Dominio y certificados | Aún no hay dominio. URLs configurables (`PUBLIC_API_URL`, `AGENT_HOST`). Con dominio: certificados públicos (sin `ca.crt`). Sin dominio: CA propia como hoy. |
| Front | Fuera de este repo. Solo consume la API. |
| Desarrollo | Se mantiene `bootstrap`. |

## Arquitectura

```text
         CENTRAL                                         CLIENTE
 Web ─HTTPS─► proxy :443 ─► auth-api                 Mosquitto del cliente
                        └─► report-api ◄──HTTPS 443── capture (misma red)
                 :8443 ─► agente ◄───────TLS 8443───────┘
                             └─ alertas ─► report-api ─► SQLite ─► ETL / Ollama
```

## Flujo

1. Web: **Agregar broker** → `POST /api/v1/brokers {name, host, port}`.
   Respuesta: el broker, `enrollment_key` (se muestra una sola vez) y
   `install_command`.
2. El cliente pega el comando. La captura llama a
   `POST /api/v1/sensors/enroll {enrollment_key}` y recibe `tenant_id`,
   `broker_id`, `sensor_id`, un token corto (24 h) y un secreto del sensor.
   Lo guarda en el volumen `/state`.
3. La captura se conecta por TLS a `agente:8443` con el token en el `hello`
   (ya existe).
4. Cada 60 s, y antes de que venza el token,
   `POST /api/v1/sensors/token/refresh {sensor_secret}` → token nuevo y
   `last_seen`.
5. El agente publica alertas en `POST /api/v1/alerts` (ya existe).
6. `GET /api/v1/brokers` incluye `status`: `pending` (sin sensor),
   `connected` (`last_seen` < 3 min) o `offline`.
7. Borrar el broker o rotar la clave invalida el secreto; el sensor queda fuera
   cuando vence su token (≤ 24 h).

## Almacenamiento

- `brokers`: `enrollment_key_hash` (SHA-256; nunca en claro).
- `sensors`: `secret_hash`, `last_seen`, `UNIQUE(broker_id)`.

## Fases

1. Backend: clave en `POST /brokers`, rotación, `enroll`, `refresh`,
   `status`. Tests y Bruno.
2. Captura: inscripción, estado en `/state`, renovación y reconexión.
3. Central de producción: proxy (Caddy), certificados, imagen de captura
   publicada.
4. `docs/instalacion.md`: Mosquitto en Docker (`--network container:`),
   nativo (`--network host`), VM en la nube; verificación y problemas comunes.

## Compatibilidad

`POST /brokers/{id}/sensors` y `POST /sensors/{id}/token` siguen existiendo para
administración, pero el flujo del cliente no los usa.
