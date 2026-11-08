# MQTT/IoT DoS detection

This project detects DoS activity in real MQTT traffic. It combines a
Mosquitto broker, a traffic simulator, a `tshark` capture sidecar, exported
machine-learning models, an alert ETL pipeline, and optional natural-language
reports generated with Ollama.

The project is a laboratory and validation environment. The simulator
generates normal traffic and DoS bursts; it does not provide attack ground
truth. The classifier assigns the final `normal` or `ataque` label from
captured traffic. The multi-attack version of the project lives in
`feature/advance_model`.

## Architecture

The project is a modular monolith. All application code lives under `src/`
and is split into two modules that do not import each other:

```text
src/
  detection/                 # always-on: capture, agent, alerts, reports
    domain/                  # Alert, FrameContext, client metadata
    application/             # Agent, per-broker worker pool and ports
    infrastructure/
      tshark/                # capture sidecar and asyncio socket server
      classifiers/           # TCP XGBoost model adapter
      sinks/                 # MQTT, daily JSONL and evidence sinks
      mqtt_client.py         # paho client factory
    reporting/               # ETL: normalize, summaries, report.json, Ollama
    http/                    # FastAPI API: reports, brokers, sensors, alerts
    composition_root.py      # wires the agent
  auth/                      # registration, email verification, JWT sessions
    domain/  application/  infrastructure/  http/
simulation/                  # lab traffic generator (not production code)
ML_Model/                    # notebooks that train and export the models
tests/
```

Inside each module the code follows Ports and Adapters: use cases depend on
port contracts, and `infrastructure/` provides the concrete adapters. Every
container sets `PYTHONPATH=/app/src`, so modules are imported as
`detection.…` and `auth.…`.

```text
simulation -> Mosquitto -> tshark capture -> Unix socket (NDJSON)
                                              |
                                   AsyncSocketServer (asyncio)
                                              |
                         BrokerPool: one worker per (tenant, broker)
                                              |
                                      Agent -> Classifier
                                              |
                              MQTT alert + daily JSONL + evidence
                                              |
                                  normalize -> summaries
                                              |
                                report.json -> Ollama report
```

In Compose, the capture container shares Mosquitto's network namespace. It
sends one NDJSON record per frame to `/capture/features.sock` in the
`capture-data` volume; the `agente` container accepts many capture connections,
runs one detection worker per broker and publishes alerts to
`alertas/deteccion`. Alerts are also written to `/alerts/YYYY-MM-DD.jsonl`
using UTC dates, and the raw frames around each alert are kept under
`/evidence/YYYY-MM-DD/<alert_id>.jsonl`. The ETL deletes evidence folders older
than `EVIDENCE_RETENTION_DAYS` (default 30).

The agent accepts up to 10 000 concurrent capture connections with an asyncio
server and runs one detection worker per `(tenant_id, broker_id)`. Each worker
has its own bounded queue; when it fills, only that broker's connection is
backpressured. The pool is capped at 256 workers and evicts workers idle for
10 minutes.

## Requirements

- Docker Engine with Docker Compose v2, or Podman with `podman-compose`.
- At least 4 GB of free memory for the containers and the Ollama model.
- The repository's Python dependencies if running commands outside Docker.
- `tshark` and capture permissions for a local, non-containerized capture.

The main image uses Python 3.11. Dependencies are listed in
[`requirements.txt`](requirements.txt). Model artifacts are already exported
under [`modelos_agente_tcp/`](modelos_agente_tcp/); do not edit them manually.

## Quick start with Compose

From the repository root:

```bash
docker compose up --build
```

The command starts the detection stack without Ollama or the simulator:

1. `certgen`, which creates the local Mosquitto and agent TLS certificates.
2. `bootstrap`, which registers the local Mosquitto as a broker, exactly like
   "Add broker" in the web, and leaves its enrollment key for the local
   capture. It is idempotent and runs before `capture` and `agente`.
3. `mosquitto`, listening on MQTT `1883` and MQTTS `8883`.
4. `report-api`, available on host port `8000`.
5. `capture` and `agente`. The capture enrolls itself with that key, as a
   customer installation does, and the agent posts every alert to
   `/api/v1/alerts`, so the per-broker reports include the simulator traffic.
6. `etl`, which periodically normalizes alerts and refreshes summaries.

Set `DEV_TENANT_ID` in `.env` to your user id (`GET /api/v1/auth/me`) so the
local broker belongs to your account. If it is empty, it is registered under the
tenant `dev`. Without `AUTH_JWT_SECRET` the agent keeps only the MQTT and JSONL
sinks. To find the local broker id:

```bash
curl -s http://localhost:8000/api/v1/brokers -H "Authorization: Bearer $ACCESS_TOKEN"
```

Ollama and the simulator are behind profiles, so they do not slow down or
generate traffic unless you ask for them.

Run the simulator against the stack:

```bash
# Normal traffic
docker compose run --rm --no-deps simulador \
  -m simulation --broker mosquitto --port 1883 --ataque none --paquetes 100

# DoS traffic
docker compose run --rm --no-deps simulador \
  -m simulation --broker mosquitto --port 1883 --ataque dos --paquetes 30000

# Or start the simulator service (default attack mode)
docker compose --profile simulator up --build
```

To watch alerts while the simulator runs:

```bash
docker compose exec mosquitto mosquitto_sub -h localhost -t alertas/deteccion -v
```

Useful lifecycle commands:

```bash
docker compose ps
docker compose logs -f agente
docker compose logs -f etl
docker compose stop
docker compose down
```

`docker compose down` removes containers and networks but keeps named volumes.
Add `-v` only when you intentionally want to delete captured data, alerts,
processed reports, and the downloaded Ollama model.

## Mosquitto

The broker configuration is in [`mosquitto/config/mosquitto.conf`](mosquitto/config/mosquitto.conf).
Port `1883` is plaintext MQTT. Port `8883` uses the self-signed certificate
generated by `certgen`. The lab broker permits anonymous connections to keep
the local setup simple; do not expose this configuration to an untrusted
network.

Inspect broker logs with:

```bash
docker compose logs -f mosquitto
docker compose exec mosquitto sh -c 'tail -f /mosquitto/log/mosquitto.log'
```

The certificates are runtime artifacts under `mosquitto/certs/` and are
ignored by Git. To force a new local certificate, stop the stack and remove
only the specific files before starting it again:

```bash
rm -f mosquitto/certs/server.crt mosquitto/certs/server.key mosquitto/certs/ca.crt
docker compose up --build
```

## Simulator

The `simulador` service is behind the `simulator` profile, so `docker compose up`
does not start it. Run it on demand:

```bash
docker compose run --rm --no-deps simulador \
  -m simulation --broker mosquitto --port 1883 --ataque dos --paquetes 500

# Or start the service with the profile
docker compose --profile simulator up --build
```

You can also run it locally against a reachable broker:

```bash
python -m simulation --broker localhost --port 1883 \
  --paquetes 500 --ataque dos --verbose
python -m simulation --dry-run --ataque dos --force-attack
```

Supported scenarios are `none` and `dos`. `--paquetes` counts MQTT
publications, not TCP frames or generated alerts. `--dos-mode flood` (default)
opens many new connections per burst, like `DoS.csv`; `--dos-mode persistent`
reuses five clients. See [`simulation/README.md`](simulation/README.md) for
scenario behavior and all options.

## Choosing and running the detector

Compose uses the TCP model only (artifacts in `modelos_agente_tcp/`). It uses
transport features, so it also works when MQTT runs over TLS on port `8883`,
as long as the capture sees the broker's packets.

The detector does not require Ollama. It can capture, classify, and persist
alerts while Ollama is stopped. Ollama is used only for natural-language
report generation.

For a local run, export `PYTHONPATH=src` and start a broker, capture, and agent in
separate terminals:

```bash
python -m detection.infrastructure.tshark.stream_features \
  --iface eth0 --filter "" \
  --exclude-topic alertas/deteccion --endpoint unix:///tmp/features.sock

python -c "from detection.composition_root import AgentConfig, build_agent; \
build_agent(AgentConfig(capture_endpoint='unix:///tmp/features.sock', \
model_dir='modelos_agente_tcp', broker_host='localhost', \
alert_dir='/tmp/alerts', evidence_dir='/tmp/evidence')).run()"

python -m simulation --broker localhost --port 1883 \
  --paquetes 30000 --ataque dos
```

## Production and customer installation

The step-by-step guide is in [`docs/instalacion.md`](docs/instalacion.md). In
short:

1. The central runs `docker-compose.yml` plus `docker-compose.prod.yml`:
   Caddy terminates HTTPS with Let's Encrypt for `API_DOMAIN`, and the agent
   listens on TLS `8443` with the certificate of `AGENT_DOMAIN`, reloaded when
   Caddy renews it.
2. The user adds a broker in the web (`POST /api/v1/brokers`). The response has
   an `enrollment_key` and an `install_command`, shown once.
3. The customer pastes the command next to their Mosquitto. The capture enrolls
   with the key (`POST /api/v1/sensors/enroll`), stores its identity in the
   `/state` volume and connects to the agent over TLS with a sensor JWT.
4. Every 60 s the capture calls `POST /api/v1/sensors/token/refresh` with its
   sensor secret. This is the heartbeat behind the broker `status`
   (`pending`, `connected`, `offline`) and renews the 24-hour token.
5. `POST /api/v1/brokers/{id}/enrollment-key` rotates the key. The installed
   capture is revoked: it can no longer refresh and the agent closes its
   connection when the current token expires.

Each broker has one capture. Reinstalling with the same key keeps the sensor id
and replaces its credentials. The customer side only opens outbound connections
to ports `443` and `8443`.

The agent mints and renews its own API token from `AUTH_JWT_SECRET`; set
`ALERT_API_TOKEN` only to use a fixed token. Tokens and keys are never logged,
and only SHA-256 hashes of enrollment keys and sensor secrets are stored.

## Ollama

Ollama is optional and lives behind the `ollama` profile. Detection and the
broker/sensor/alert API work without it; only `/api/v1/reports` needs Ollama.
Start it explicitly:

```bash
OLLAMA_MODEL=gemma3:4b docker compose --profile ollama up -d --build
curl http://localhost:11435/api/tags
docker compose --profile ollama exec ollama ollama list
```

Use another model or host port with:

```bash
OLLAMA_MODEL=llama3.2:3b OLLAMA_PORT=11436 \
  docker compose --profile ollama up -d --build
```

The initializer pulls the selected model before `natural-report` runs. If Ollama
is not started, detection continues and `/api/v1/reports` returns `502`.

## ETL and analytical summaries

The `etl` service runs every 300 seconds by default. It does not call Ollama.
It normalizes JSONL alerts, builds idempotent summaries, and generates
`/processed/report.json` for downstream services. Change the interval with:

```bash
ETL_INTERVAL_SECONDS=60 docker compose up --build -d
```

Report timestamps are written in `America/Bogota` by default (UTC-5). Change
the output timezone with `REPORT_TIMEZONE`, for example:

```bash
REPORT_TIMEZONE=America/Bogota docker compose up -d
```

Each ETL cycle also prunes evidence folders by UTC date. Set
`EVIDENCE_RETENTION_DAYS` (default 30) and optionally `ALERT_RETENTION_DAYS`
(default 0, disabled) to delete old daily alert files after they are normalized:

```bash
EVIDENCE_RETENTION_DAYS=15 ALERT_RETENTION_DAYS=90 docker compose up -d
```

Run the ETL stages manually:

```bash
docker compose --profile etl run --rm normalize
docker compose --profile etl run --rm summaries
```

The normalized output contains `alerts.parquet`, `processing_errors.jsonl`, and
`duplicates.jsonl`. Summary Parquet files are written under `runs/`, `clients/`,
`ips/`, `topics/`, and `temporal/`, together with `checkpoint.json`.
Summaries are deduplicated by `alert_id` and written atomically, so repeating
the command does not double-count the same alerts.

The commands above use container paths and should be run through Compose when
the data is in named volumes. To inspect processed files:

```bash
docker run --rm -v agent_iot_processed-data:/processed alpine \
  find /processed -type f -print
```

The exact volume prefix depends on the Compose project name. The portable
alternative below uses the volumes already mounted by the project services:

```bash
# List all files produced by normalization, summaries, and reports
docker compose --profile etl run --rm --entrypoint sh report \
  -c 'find /processed -type f -printf "%p (%s bytes)\n" | sort'

# List normalized alert files
docker compose --profile etl run --rm --entrypoint sh normalize \
  -c 'find /alerts/normalized -maxdepth 1 -type f -print | sort'

# List every summary partition
docker compose --profile etl run --rm --entrypoint sh summaries \
  -c 'find /processed/summaries -type f -print | sort'
```

The summary files are Parquet files. To inspect their schema and rows, use a
temporary Python process with the same project image:

```bash
docker compose --profile etl run --rm --entrypoint python summaries -c '
import pandas as pd
from pathlib import Path

root = Path("/processed/summaries")
for path in sorted(root.glob("*/summary.parquet")):
    frame = pd.read_parquet(path)
    print(f"\n== {path} ==")
    print(f"rows={len(frame)} columns={list(frame.columns)}")
    print(frame.head(5).to_string(index=False))
'
```

The generated files have these purposes:

| Path | Contents |
|---|---|
| `/alerts/normalized/alerts.parquet` | Validated and normalized alerts. |
| `/alerts/normalized/processing_errors.jsonl` | Invalid input lines and validation errors. |
| `/alerts/normalized/duplicates.jsonl` | Duplicate alerts detected by the pipeline. |
| `/processed/summaries/runs/summary.parquet` | Overall alert-run statistics. |
| `/processed/summaries/clients/summary.parquet` | Aggregates by client. |
| `/processed/summaries/ips/summary.parquet` | Aggregates by source IP. |
| `/processed/summaries/topics/summary.parquet` | Aggregates by MQTT topic. |
| `/processed/summaries/temporal/summary.parquet` | One-minute activity windows. |
| `/processed/summaries/checkpoint.json` | Input fingerprint and summary checkpoint. |
| `/processed/report.json` | Combined analytical report sent to Ollama. |
| `/processed/report.md` | Optional natural-language report when `--output` is used. |

To read the final JSON or Markdown report:

```bash
docker compose --profile etl run --rm --entrypoint sh report \
  -c 'test -f /processed/report.json && cat /processed/report.json || echo "report.json does not exist yet"'

docker compose --profile etl run --rm --entrypoint sh report \
  -c 'test -f /processed/report.md && cat /processed/report.md || echo "report.md does not exist yet"'
```

The `etl` service runs continuously and logs each polling cycle. Follow its
progress and inspect the generated files repeatedly from separate terminals:

```bash
docker compose logs -f etl
watch -n 5 "docker compose --profile etl run --rm --quiet-pull --entrypoint sh report -c 'find /processed -type f -printf \"%p %s bytes\\n\" | sort'"
```

The automatic ETL updates normalized alerts, summaries, and `report.json`. It
does not call Ollama. Run the report stage manually only when needed:

```bash
docker compose --profile etl run --rm report
docker compose --profile etl run --rm natural-report \
  --output /processed/report.md
```

The report services mount `processed-data`, so the files remain available after
the one-shot containers exit. They are removed only if the named volume is
deleted, for example with `docker compose down -v`.

## Reports

### Complete manual pipeline

[`generar_reporte.sh`](generar_reporte.sh) runs a complete demonstration:

```bash
chmod +x generar_reporte.sh
./generar_reporte.sh
```

It builds and starts the stack, waits for the simulator, stops capture/agent/
ETL so files are complete, then runs normalization, summaries, `report.json`,
and the Ollama stage. The script prints the natural-language report. The
timeout can be changed with `OLLAMA_TIMEOUT=600`.

The Compose `natural-report` command prints the response unless an output path
is supplied. To persist it explicitly:

```bash
docker compose --profile etl run --rm natural-report \
  --output /processed/report.md
```

Generate the analytical JSON without Ollama:

```bash
docker compose --profile etl run --rm report
```

Generate the Markdown report from the JSON:

```bash
docker compose --profile etl run --rm natural-report \
  --output /processed/report.md
```

For a local installation, the equivalent commands are:

```bash
python -m detection.reporting.report \
  --input /processed/summaries --output /processed/report.json
python -m detection.reporting.natural_report \
  --input /processed/report.json --output /processed/report.md \
  --ollama-url http://localhost:11435 --ollama-model gemma3:4b
```

Reports use the latest 24-hour UTC window. A historical fallback is selected
when no summaries overlap the requested window but historical summaries exist.
To request a historical reference in the Compose report stage:

```bash
docker compose --profile etl run --rm --entrypoint python report \
  -m detection.reporting.report \
  --input /processed/summaries --output /processed/report.json \
  --now 2026-11-03T20:44:16Z
```

## REST API

The API is served by `report-api` on `http://localhost:8000`. Reports are
built per tenant from the alerts stored in `DETECTION_DB_PATH`, so every
report endpoint requires the user access token and only covers the caller's
alerts. Pass `broker_id` to limit the report to one of the caller's brokers:

```bash
curl http://localhost:8000/health

# Analytical JSON (no Ollama needed)
curl "http://localhost:8000/api/v1/reports/analytics?broker_id=$BROKER_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Natural-language report generated by Ollama
curl -X POST http://localhost:8000/api/v1/reports \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"broker_id":"'$BROKER_ID'"}'
```

Response shape of `POST /api/v1/reports`:

```json
{"report":"## Summary\n..."}
```

The JSON report has the same shape as `report.json`, plus `scope`
(`tenant_id`, `broker_id`, `broker_name`) and `brokers`, the alert count per
broker in the selected period. The request body is optional. It can specify
`broker_id`, a model and a timezone-aware reference timestamp:

```bash
curl -X POST http://localhost:8000/api/v1/reports \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"gemma3:4b","now":"2026-11-07T12:00:00Z"}'
```

Reports cover the 24 hours before `now`. When that window has no alerts, the
report uses the 24 hours ending at the caller's latest alert and sets
`period.historical_fallback`. The API returns `401` without a valid token,
`404` when the broker is not the caller's or there are no alerts, `400` for an
invalid timestamp, and `502` when Ollama cannot generate the report. The
global `/processed/report.json` written by the ETL is still produced for the
CLI, but the API no longer serves it.

### Brokers, sensors and alerts

The same FastAPI app stores the broker/sensor registry and the alerts in
`DETECTION_DB_PATH` (SQLite). User endpoints require the access token issued by
the auth service (`Authorization: Bearer <access_token>`); the tenant is the
token `sub`.

```bash
# Register a broker: returns enrollment_key and install_command (shown once)
curl -X POST http://localhost:8000/api/v1/brokers \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"bodega","host":"mqtt.example.com","port":1883}'

# Broker status: pending, connected or offline
curl http://localhost:8000/api/v1/brokers/$BROKER_ID \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# New key (the installed capture is revoked)
curl -X POST http://localhost:8000/api/v1/brokers/$BROKER_ID/enrollment-key \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# The capture container calls these itself
curl -X POST http://localhost:8000/api/v1/sensors/enroll \
  -H 'Content-Type: application/json' -d '{"enrollment_key":"ek_..."}'
curl -X POST http://localhost:8000/api/v1/sensors/token/refresh \
  -H "Authorization: Bearer $SENSOR_SECRET"

# Alerts can be posted with a sensor or agent token
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Authorization: Bearer $SENSOR_TOKEN" -H 'Content-Type: application/json' \
  -d '{"alert_id":"a-1","ts":1800000000,"kind":"class","label":"ataque"}'

# Delete a broker; its sensors cascade, alerts are kept
curl -X DELETE http://localhost:8000/api/v1/brokers/$BROKER_ID \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`GET /api/v1/alerts` returns only the caller's alerts, newest first. It accepts
`limit` (1-1000), `broker_id`, `sensor_id`, `since` (inclusive) and `until`
(exclusive); the time filters take epoch seconds or ISO-8601 with a timezone,
for example `?since=2026-11-08T00:00:00Z&until=2026-11-09T00:00:00Z`.
`POST /api/v1/alerts` also
appends the alert to `/alerts/YYYY-MM-DD.jsonl`, so the existing ETL and reports
keep working. `DELETE /api/v1/brokers/{id}` removes the broker and its sensor
(cascade) but keeps its alerts for auditing. With `ENROLL_KEY` the capture
takes its tenant, broker and sensor ids from the enrollment; without it, it
reads `TENANT_ID`, `BROKER_ID` and `SENSOR_ID` (or the matching flags).
`POST /brokers/{id}/sensors` and `POST /sensors/{id}/token` remain for
administration; a broker accepts a single sensor (`409` otherwise).

### Bruno collection

Manual API tests live in [`bruno/AgentIoT/`](bruno/AgentIoT/). Open that folder in
Bruno, select the `Local` environment and run the folders in order. The
collection registers a user, creates a broker and sensor, issues tokens, ingests
alerts, checks idempotency and tenant isolation, and deletes the broker while
keeping its alerts. Tokens are secret environment variables and are not stored
in the repository.

From the terminal, run the CLI from the collection root (or use the wrapper,
which handles the `cd`):

```bash
./bruno/run.sh --env Local
./bruno/run.sh 01-auth --env Local
```

## Models, data, and limitations

The notebooks live in [`ML_Model/`](ML_Model/):

- `01_eda_politica.ipynb` cleans the data and defines the column policy. The
  task is DoS vs normal; MitM and Intrusion captures contribute only their
  normal traffic.
- `02_tcp_vs_mqtt.ipynb` compares the MQTT feature set with the TCP-only set.
- `03_modelo_tcp.ipynb` trains the TCP model and exports
  [`modelos_agente_tcp/`](modelos_agente_tcp/).

The feature order is defined by `pipeline_config.json`; changing features
requires retraining and re-exporting. No model uses raw application payloads as
features.

The TCP model was trained with a single DoS capture, a flood of new
connections, and relies heavily on `tcp_new_conns_5s`. With `--dos-mode
persistent` it detects a much smaller share of the attacker's frames. Its TLS
robustness was estimated by padding frame sizes, not with real MQTTS captures.

Frames are grouped by `(tcp.stream, ip.src, tcp.srcport, ip.dst, tcp.dstport)`.
The capture keeps `ip.dst` and `tcp.stream` as context without using them as ML
features. Older JSONL records without the required endpoint fields are skipped
in per-flow mode. MQTT `client_id` and the latest topic are correlated by
`tcp.stream` when CONNECT and PUBLISH frames provide them.

TLS traffic on port `8883` can be captured with a filter such as
`tcp.port == 8883`, but encrypted payloads cannot be decoded by the `mqtt`
display filter without decryption.

## Tests

Run the complete unit-test suite from the repository root:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Additional component documentation is available in
[`src/detection/application/use_cases/README.md`](src/detection/application/use_cases/README.md),
[`src/detection/infrastructure/classifiers/README.md`](src/detection/infrastructure/classifiers/README.md),
[`src/detection/infrastructure/sinks/README.md`](src/detection/infrastructure/sinks/README.md),
[`src/detection/infrastructure/tshark/README.md`](src/detection/infrastructure/tshark/README.md), and
[`mosquitto/README.md`](mosquitto/README.md).
