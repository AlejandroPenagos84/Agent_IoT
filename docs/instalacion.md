# Guía de instalación

Esta guía cubre las dos partes del sistema:

1. **La central:** API, agente de detección y reportes. La instalas tú una vez.
2. **La captura:** un contenedor por broker MQTT. La instala cada cliente junto
   a su Mosquitto, en la nube o en su red local.

```text
          CENTRAL (tu servidor)                         CLIENTE
 Web ──HTTPS──► Caddy :443 ─► auth-api              Mosquitto del cliente
                          └─► report-api ◄─HTTPS 443─ captura (misma red)
                :8443 ─► agente ◄──────────TLS 8443──────┘
```

La captura solo abre conexiones **de salida** a los puertos 443 y 8443. El
cliente no abre puertos de entrada ni toca su NAT.

## 1. Central

### Requisitos

- Linux con Docker Engine 24+ y Docker Compose v2.
- 4 GB de RAM (8 GB si usas Ollama para los reportes en texto).
- Dos nombres DNS que apunten a la IP pública del servidor, por ejemplo
  `api.tudominio.com` y `agent.tudominio.com`.
- Puertos de entrada abiertos: `80` y `443` (Caddy y Let's Encrypt) y `8443`
  (agente).

### Pasos

1. Clona el repositorio y crea el `.env`:
   ```bash
   cp .env.example .env
   openssl rand -hex 32   # pega el resultado en AUTH_JWT_SECRET
   ```
2. Completa en `.env`:
   ```env
   AUTH_JWT_SECRET=<64 caracteres hex>
   API_DOMAIN=api.tudominio.com
   AGENT_DOMAIN=agent.tudominio.com
   ACME_EMAIL=tu@correo.com
   CAPTURE_IMAGE=ghcr.io/<tu-org>/agentiot-capture:latest
   ```
   Configura también el SMTP real de `AUTH_SMTP_*` para los correos de
   verificación.
3. Levanta auth y la central:
   ```bash
   docker compose -f docker-compose.auth.yml up -d --build
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```
4. Publica la imagen de la captura para que los clientes la descarguen:
   ```bash
   docker build -f Dockerfile.capture -t ghcr.io/<tu-org>/agentiot-capture:latest .
   docker push ghcr.io/<tu-org>/agentiot-capture:latest
   ```
5. Verifica:
   ```bash
   curl https://api.tudominio.com/health          # {"status":"ok"}
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
   ```

Caddy obtiene y renueva los certificados de Let's Encrypt. El agente usa el
certificado de `AGENT_DOMAIN` y lo recarga solo cuando Caddy lo renueva, así que
los clientes no necesitan instalar ninguna CA.

### Sin dominio público (laboratorio)

Sin dominio, Let's Encrypt no puede emitir certificados. Usa las CA locales:

```env
CADDY_EXTRA_GLOBAL=local_certs     # Caddy firma con su CA interna
AGENT_CERT_MODE=self-signed        # el agente usa la CA de certgen
AGENT_CA_PATH=/certs/agent/ca.crt  # la API entrega esa CA a cada captura
AGENT_DOMAIN=agente                # debe coincidir con el certificado de certgen
```

En este modo la captura necesita la CA de Caddy para hablar con la API (ver
[Problemas comunes](#problemas-comunes)).

### Docker rootless

Docker rootless no puede abrir puertos menores que 1024. Usa
`HTTP_PORT=8080 HTTPS_PORT=8444` y redirige los puertos 80 y 443 en el
firewall, o instala Docker con root.

## 2. Alta de un broker (cliente)

1. El cliente entra a la web y pulsa **Agregar broker** (nombre, host y puerto).
2. La web le muestra un comando como este, **una sola vez**:
   ```bash
   docker run -d --name agentiot-capture --restart unless-stopped \
     --network container:mosquitto --cap-add NET_RAW \
     -v agentiot-capture-state:/state \
     -e ENROLL_KEY=ek_... \
     -e API_URL=https://api.tudominio.com \
     ghcr.io/<tu-org>/agentiot-capture:latest
   ```
3. El cliente lo pega en el servidor de su broker (ver los casos abajo).
4. En unos segundos el broker pasa de **Esperando captura** (`pending`) a
   **Conectado** (`connected`).

Si pierde el comando, pulsa **Generar nueva clave**. Eso invalida la clave
anterior y desconecta la captura instalada hasta que se reinstale con la nueva.

### Caso A: Mosquitto en Docker

Cambia `mosquitto` en `--network container:mosquitto` por el nombre del
contenedor del broker:

```bash
docker ps --format '{{.Names}}\t{{.Image}}' | grep -i mosquitto
```

La captura comparte la red del broker y ve todo su tráfico.

Si el broker está en un proyecto Compose, puedes usar
`docker-compose.capture.yml` en vez del `docker run`:

```bash
ENROLL_KEY=ek_... API_URL=https://api.tudominio.com \
MOSQUITTO_CONTAINER=<nombre-del-contenedor> \
  docker compose -f docker-compose.capture.yml up -d
```

### Caso B: Mosquitto instalado en el sistema (sin Docker)

Usa la red del host y la interfaz por la que llegan los clientes MQTT:

```bash
ip -br addr          # p. ej. eth0, ens5, enp0s3
docker run -d --name agentiot-capture --restart unless-stopped \
  --network host --cap-add NET_RAW \
  -v agentiot-capture-state:/state \
  -e ENROLL_KEY=ek_... -e API_URL=https://api.tudominio.com \
  ghcr.io/<tu-org>/agentiot-capture:latest --iface ens5
```

### Caso C: VM en la nube (AWS, Huawei Cloud, GCP, Azure)

Es igual al caso A o B, según cómo corra Mosquitto. Comprueba también:

- Que el *security group* o firewall permita **salida** a `443` y `8443` hacia
  la central. La entrada solo la necesita el propio broker (1883 u 8883).
- Que la interfaz de la VM sea la correcta (`ens5` en AWS Nitro, `eth0` en
  muchas otras).

### Qué hace la captura

1. La primera vez, se inscribe con `ENROLL_KEY` y guarda su identidad en el
   volumen `agentiot-capture-state`. Si se reinicia, no crea un sensor nuevo.
2. Envía al agente, por TLS, solo las métricas TCP de cada trama. No envía
   contraseñas, usuarios ni el contenido de los mensajes.
3. Cada 60 s avisa a la API que sigue viva y renueva su token, que dura 24 h.
4. Si la clave se rota o el broker se borra, deja de enviar datos.

## 3. Verificación

En el servidor del cliente:

```bash
docker logs agentiot-capture
# [enroll] inscrito: broker=... sensor=...
# Capturing on 'eth0'
```

En la web, o con la API:

```bash
curl -s https://api.tudominio.com/api/v1/brokers -H "Authorization: Bearer $ACCESS_TOKEN"
# "status": "connected", "last_seen": "..."
```

Cuando haya tráfico de ataque, las alertas aparecen en
`GET /api/v1/alerts?broker_id=...` y en
`GET /api/v1/reports/analytics?broker_id=...`.

## Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `inscripción rechazada: HTTP 401` | La clave es incorrecta, se rotó o el broker se borró. Genera una nueva en la web. |
| `API no disponible ...; reintento` | La captura no llega a `API_URL`. Revisa el DNS y la salida al puerto 443. Reintenta sola. |
| `CERTIFICATE_VERIFY_FAILED` con la API | La API usa una CA privada (laboratorio). Monta la CA y pásala: `-v ./caddy-root.crt:/certs/api-ca.crt:ro -e API_CA=/certs/api-ca.crt`. |
| Estado `connected`, pero sin alertas | La captura no ve el tráfico del broker. Revisa `--network container:<broker>` o `--iface`. Prueba con `docker exec agentiot-capture tshark -i eth0 -c 5 -f "tcp port 1883"`. |
| Estado `offline` | La captura está detenida o sin salida a la API. Mira `docker logs agentiot-capture`. Si dice `sensor revocado`, reinstala con una clave nueva. |
| `Operation not permitted` al capturar | Falta `--cap-add NET_RAW`. |
| Reinstalé en otra máquina y la primera dejó de funcionar | Es lo esperado: un broker tiene una sola captura. La última inscripción reemplaza a la anterior. |

## Desinstalar

```bash
docker rm -f agentiot-capture
docker volume rm agentiot-capture-state
```

Después borra el broker en la web. Sus alertas se conservan para auditoría.
