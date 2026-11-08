# Bruno — Agent IoT API

Colección para probar la API de autenticación y la API de detección.

## Antes de correr

1. Levanta los servicios de auth:
   ```bash
   docker compose -f docker-compose.auth.yml up -d --build
   ```
   Usa la configuración SMTP de `.env`. Si el código no cae en Mailhog, pégalo
   manualmente en la variable `emailCode`.

2. Levanta la API de detección:
   ```bash
   docker compose up -d --build
   ```
   Esto arranca `mosquitto`, `capture`, `agente`, `etl` y `report-api`, sin
   Ollama ni simulador. Ollama solo hace falta para `/reports`.

3. En Bruno, abre esta colección y selecciona el environment **Local**.

## Ejecutar desde la CLI

El CLI de Bruno debe ejecutarse **desde la raíz de la colección**, no desde la
raíz del repositorio pasando la ruta. Con Node instalado:

```bash
cd bruno/AgentIoT
npx @usebruno/cli run --env Local

# Solo una carpeta
npx @usebruno/cli run 01-auth --env Local
```

O usa el wrapper desde cualquier directorio:

```bash
./bruno/run.sh --env Local
./bruno/run.sh 01-auth --env Local
```

Si ves `You can run only at the root of a collection`, estás ejecutando desde
fuera de `bruno/AgentIoT` o pasaste la ruta de la colección como argumento.

## Flujo

Las carpetas están numeradas para ejecutarse en orden:

1. `01-auth`: health, registro, código de Mailhog, verificación, login y `/me`.
2. `02-brokers`: crear el broker (devuelve la clave de inscripción), inscribir la
   captura como lo hace el contenedor, renovar el token, ver el estado, rotar la
   clave y reinstalar.
3. `03-alerts`: ingesta con token de sensor, listar, obtener, duplicado y token de agente.
4. `04-reports`: reporte JSON por broker (sin Ollama) y reporte natural (requiere Ollama).
5. `99-cleanup`: borrar broker, comprobar que sensores dan 404 y que las alertas siguen.

Los scripts de post-response guardan en el environment:

- `tenantId` al registrar o consultar `/me`.
- `accessToken` al hacer login.
- `brokerId` al crear el broker.
- `enrollmentKey` al crear el broker o rotar la clave.
- `sensorId`, `sensorToken` y `sensorSecret` al inscribir la captura.
- `alertId` al ingerir la alerta.
- `emailCode` desde Mailhog.

Los tokens y claves (`accessToken`, `sensorToken`, `agentToken`, `enrollmentKey`,
`sensorSecret`) son variables secretas:
Bruno no guarda sus valores en el archivo del environment.

## Token de agente

La API no emite tokens de agente. Genéralo con el CLI y pégalo en la variable
secreta `agentToken` de Bruno:

```bash
AUTH_JWT_SECRET=... PYTHONPATH=src python -m detection.infrastructure.sensor_tokens \
  --agent --ttl-minutes 10080
```

Si quieres limitarlo a un tenant, añade `--tenant-id <user_id>`.

## Notas

- El email de registro es fijo (`tester@example.com`). Para repetir el flujo
  desde cero, borra el volumen de auth:
  `docker compose -f docker-compose.auth.yml down -v`.
- Si ejecutas `99-cleanup`, las alertas se conservan, pero el broker y sus
  sensores desaparecen. Vuelve a correr desde `02-brokers` para recrearlos.
- Los reportes usan las alertas del usuario guardadas en la API, no el
  `report.json` del ETL. Devuelven 404 si el broker no es tuyo o si no hay
  alertas; corre antes `03-alerts`.
- El agent token debe incluir `tenant_id` en la alerta; si el token fue creado
  con `--tenant-id`, debe coincidir.
