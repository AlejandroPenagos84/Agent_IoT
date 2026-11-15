# Guía de instalación

Esta guía cubre la instalación en **producción**:

1. **La central:** API, agente de detección y retención. La instalas tú una vez.
2. **La captura:** un contenedor por broker MQTT. La instala cada cliente junto
   a su Mosquitto, en la nube o en su red local.

Para probar todo en una sola máquina (central, Mosquitto de prueba, captura y
simulador), sigue [`deploy/README.md`](../deploy/README.md), sección *Local*.

```text
          CENTRAL (tu servidor)                          CLIENTE
 Web ──HTTPS──► Caddy :443 ──► app :8000 (API)       Mosquitto del cliente
                               ▲     ◄──HTTPS 443──── captura (misma red)
                :8443 ────► app :8443 (agente) ◄──TLS 8443──┘
```

La central es un solo proceso `app` (API de auth y detección + agente que
recibe las capturas), más `redis` (códigos de verificación), `caddy` (HTTPS y
certificados) y `certgen` (certificados autofirmados para laboratorio).

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

1. Clona el repositorio y crea el `.env` (cópialo: `.env.example` está en git):
   ```bash
   cp .env.example .env
   openssl rand -hex 32   # pega el resultado en AUTH_JWT_SECRET
   ```
2. Completa en `.env`:
   ```env
   AUTH_JWT_SECRET=<64 caracteres hex>
   AUTH_COOKIE_SECURE=true

   # .env.example trae 8080/8444 para Docker rootless; Let's Encrypt necesita 80/443
   HTTP_PORT=80
   HTTPS_PORT=443

   # Caddy emite con Let's Encrypt los certificados de ambos dominios
   API_DOMAIN=api.tudominio.com
   AGENT_DOMAIN=agent.tudominio.com
   ACME_EMAIL=tu@correo.com

   # El agente usa el certificado que Caddy emitió para AGENT_DOMAIN
   TLS_CERT=/caddy/caddy/certificates/acme-v02.api.letsencrypt.org-directory/agent.tudominio.com/agent.tudominio.com.crt
   TLS_KEY=/caddy/caddy/certificates/acme-v02.api.letsencrypt.org-directory/agent.tudominio.com/agent.tudominio.com.key

   # Lo que recibe cada captura al inscribirse
   PUBLIC_API_URL=https://api.tudominio.com
   AGENT_PUBLIC_ENDPOINT=tls://agent.tudominio.com:8443
   AGENT_TLS_SERVER_NAME=agent.tudominio.com
   AGENT_CA_PATH=
   CAPTURE_IMAGE=ghcr.io/<tu-org>/agentiot-capture:latest
   ```
   `AGENT_CA_PATH` vacío significa que el agente usa una CA pública: las
   capturas lo verifican con las CA del sistema y no hay que instalarles nada.

   Configura también el SMTP real (`AUTH_SMTP_HOST`, `AUTH_SMTP_PORT`,
   `AUTH_SMTP_USERNAME`, `AUTH_SMTP_PASSWORD`, `AUTH_SMTP_FROM`). Sin
   `AUTH_SMTP_HOST`, los correos de verificación se escriben en el log de `app`,
   lo que solo sirve en desarrollo.
3. Levanta la central:
   ```bash
   docker compose up -d --build
   ```
   En el primer arranque la API responde enseguida, pero el agente espera a que
   Caddy obtenga el certificado de `AGENT_DOMAIN` (en el log de `app`:
   `agente esperando certificados: ...`). Después recarga solo los
   certificados renovados, sin reiniciar.
4. Publica la imagen de la captura para que los clientes la descarguen:
   ```bash
   docker build -f Dockerfile.capture -t ghcr.io/<tu-org>/agentiot-capture:latest .
   docker push ghcr.io/<tu-org>/agentiot-capture:latest
   ```
5. Verifica:
   ```bash
   curl https://api.tudominio.com/health          # {"status":"ok"}
   docker compose ps                              # app "healthy"
   ```

Ollama, para los reportes en lenguaje natural, es opcional:
`docker compose --profile ollama up -d`.

### Sin dominio público (laboratorio)

Sin dominio, Let's Encrypt no puede emitir certificados. Usa las CA locales:

```env
CADDY_EXTRA_GLOBAL=local_certs             # Caddy firma la API con su CA interna
TLS_CERT=/certs/agent/server.crt           # certificado de certgen (valor por defecto)
TLS_KEY=/certs/agent/server.key
AGENT_CA_PATH=/certs/agent/ca.crt          # la API entrega esta CA a cada captura
AGENT_PUBLIC_ENDPOINT=tls://<ip-o-host-del-servidor>:8443
AGENT_TLS_SERVER_NAME=app                  # debe estar en el SAN del certificado de certgen
PUBLIC_API_URL=https://<ip-o-host-del-servidor>
```

`certgen` emite el certificado del agente con SAN `app`, `localhost` y
`127.0.0.1`. La captura se conecta a la IP que diga `AGENT_PUBLIC_ENDPOINT` pero
verifica el nombre `AGENT_TLS_SERVER_NAME`, así que `app` funciona aunque se
conecte por IP.

En este modo la captura necesita además la CA de Caddy para hablar con la API
(ver [Problemas comunes](#problemas-comunes)).

### Docker rootless

Docker rootless no puede abrir puertos menores que 1024. Usa
`HTTP_PORT=8080 HTTPS_PORT=8444` (los valores de `.env.example`) y redirige los
puertos 80 y 443 en el firewall, o instala Docker con root.

## 2. Alta de un broker (cliente)

1. El cliente entra a la web y pulsa **Agregar broker** (nombre, host y puerto).
   Por API es `POST /api/v1/brokers`.
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

Si pierde el comando, pulsa **Generar nueva clave**
(`POST /api/v1/brokers/<id>/enrollment-key`). Eso invalida la clave anterior y
desconecta la captura instalada hasta que se reinstale con la nueva.

### Caso A: Mosquitto en Docker

Cambia `mosquitto` en `--network container:mosquitto` por el nombre del
contenedor del broker:

```bash
docker ps --format '{{.Names}}\t{{.Image}}' | grep -i mosquitto
```

La captura comparte la red del broker y ve todo su tráfico. Su propio tráfico
hacia la central también pasa por esa interfaz, pero se ignora: solo procesa
tramas de los puertos 1883 y 8883.

Si el broker está en un proyecto Compose, puedes usar
`docker-compose.capture.yml` en vez del `docker run`:

```bash
ENROLL_KEY=ek_... API_URL=https://api.tudominio.com \
MOSQUITTO_CONTAINER=<nombre-del-contenedor> \
CAPTURE_IMAGE=ghcr.io/<tu-org>/agentiot-capture:latest \
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
   volumen `agentiot-capture-state`. Si se reinicia, reutiliza esa identidad y
   no crea un sensor nuevo.
2. Se conecta al agente por TLS, verificando su certificado, y se presenta con
   su token. Envía solo las métricas TCP de cada trama: nunca contraseñas,
   usuarios ni el contenido de los mensajes.
3. Cada 60 s avisa a la API que sigue viva. El token dura 24 h y se renueva
   cuando pasa la mitad de su vida; la captura se reconecta sola con el nuevo.
4. Si la clave se rota o el broker se borra, deja de enviar datos y no se
   vuelve a inscribir con la clave vieja.

## 3. Verificación

En el servidor del cliente:

```bash
docker logs agentiot-capture
# [enroll] inscrito: broker=... sensor=...
# Capturing on 'eth0'
# [capture] socket {"sent": 1234, "dropped": 0, "reconnects": 0}   (cada 60 s)
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
| `docker run`: *name already in use* | Quedó una captura anterior: `docker rm -f agentiot-capture`. |
| `pull access denied for ...agentiot-capture` | La imagen no está publicada o el nombre no coincide con `CAPTURE_IMAGE`. |
| `inscripción rechazada: HTTP 401` | La clave es incorrecta, se rotó o el broker se borró. Genera una nueva en la web. |
| `API no disponible ...; reintento` | La captura no llega a `API_URL`. Revisa el DNS y la salida al puerto 443. Reintenta sola. |
| `CERTIFICATE_VERIFY_FAILED` con la API | La API usa una CA privada (laboratorio). Monta la CA y pásala: `-v ./caddy-root.crt:/certs/api-ca.crt:ro -e API_CA=/certs/api-ca.crt`. |
| `CERTIFICATE_VERIFY_FAILED` con el agente | `AGENT_TLS_SERVER_NAME` no está en el certificado del agente, o la CA cambió después de la inscripción (por ejemplo, `certgen` regeneró). Corrige la central, borra `agentiot-capture-state` y reinstala con una clave nueva. |
| Estado `connected`, pero sin alertas | La captura no ve el tráfico del broker. Revisa `--network container:<broker>` o `--iface`. Prueba con `docker exec agentiot-capture tshark -i eth0 -c 5 -f "tcp port 1883"`. Con tráfico normal no hay alertas: es lo esperado. |
| Estado `offline` | La captura está detenida o sin salida a la API. Mira `docker logs agentiot-capture`. Si dice `sensor revocado`, reinstala con una clave nueva. |
| `Operation not permitted` al capturar | Falta `--cap-add NET_RAW`. |
| La API responde pero las capturas no conectan al 8443, y el log de `app` dice `agente esperando certificados` | Caddy aún no emitió el certificado de `AGENT_DOMAIN`, o `TLS_CERT`/`TLS_KEY` apuntan a otra ruta. Revisa el DNS, los puertos 80/443 y `docker compose logs caddy`. |
| Reinstalé en otra máquina y la primera dejó de funcionar | Es lo esperado: un broker tiene una sola captura. La última inscripción reemplaza a la anterior. |

## Desinstalar

```bash
docker rm -f agentiot-capture
docker volume rm agentiot-capture-state
```

Después borra el broker en la web. Sus alertas se conservan para auditoría.
