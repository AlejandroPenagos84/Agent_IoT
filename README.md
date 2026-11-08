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
    application/             # Agent use case and its ports
    infrastructure/
      tshark/                # capture sidecar and JSONL feature source
      classifiers/           # TCP, LSTM, XGBoost and hybrid models
      sinks/                 # MQTT and daily JSONL alert sinks
      mqtt_client.py         # paho client factory
    reporting/               # ETL: normalize, summaries, report.json, Ollama
    http/                    # FastAPI report API (/api/v1/reports)
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
simulation -> Mosquitto -> tshark capture -> features.jsonl
                                              |
                                      TsharkFeatureSource
                                              |
                                      Agent -> Classifier
                                              |
                              MQTT alert + daily JSONL
                                              |
                                  normalize -> summaries
                                              |
                                report.json -> Ollama report
```

In Compose, the capture container shares Mosquitto's network namespace. It
writes `/capture/features.jsonl` to the `capture-data` volume. The `agente`
container tails that file, groups frames by connection and direction, and
publishes alerts to `alertas/deteccion`. Alerts are also written to
`/alerts/YYYY-MM-DD.jsonl` using UTC dates.

## Requirements

- Docker Engine with Docker Compose v2, or Podman with `podman-compose`.
- At least 4 GB of free memory for the containers and the Ollama model.
- The repository's Python dependencies if running commands outside Docker.
- `tshark` and capture permissions for a local, non-containerized capture.

The main image uses Python 3.11. Dependencies are listed in
[`requirements.txt`](requirements.txt). Model artifacts are already exported
under [`modelos_agente_tcp/`](modelos_agente_tcp/) (TCP model) and
[`modelos_agente/`](modelos_agente/) (MQTT models); do not edit them manually.

## Quick start with Compose

From the repository root:

```bash
docker compose up --build
```

The command starts:

1. `certgen`, which creates the local Mosquitto TLS certificates if needed.
2. `mosquitto`, listening on MQTT `1883` and MQTTS `8883`.
3. `ollama` and `ollama-init`, which download the configured model.
4. `capture`, `agente`, and the default `simulador`.
5. `etl`, which periodically normalizes alerts and refreshes summaries.
6. `report-api`, available on host port `8000`.

The simulator is configured with `ATAQUE` (`none` or `dos`, default `dos`),
`DOS_MODE` (`flood` or `persistent`, default `flood`) and `PAQUETES` (default
`30000`, three flood bursts):

```bash
ATAQUE=none PAQUETES=100 docker compose up --build
DOS_MODE=persistent docker compose up --build
MODELO=hybrid docker compose up --build
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

Run the simulator inside Compose or locally against a reachable broker:

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

Compose uses the TCP model by default (`MODELO=tcp`, artifacts in
`modelos_agente_tcp/`). Valid values are `tcp`, `lstm`, `hybrid`, and
`xgboost`; the last three load `modelos_agente/`:

```bash
MODELO=hybrid docker compose up --build
```

The TCP model only uses transport features, so it also works when MQTT runs
over TLS on port `8883`, as long as the capture sees the broker's packets. The
MQTT models (`lstm`, `hybrid`, `xgboost`) need decoded MQTT fields and only
work on plaintext traffic.

The detector does not require Ollama. It can capture, classify, and persist
alerts while Ollama is stopped. Ollama is used only for natural-language
report generation.

For a local run, export `PYTHONPATH=src` and start a broker, capture, and agent in
separate terminals:

```bash
python -m detection.infrastructure.tshark.stream_features \
  --iface eth0 --filter "" \
  --exclude-topic alertas/deteccion --out /tmp/features.jsonl

python -c "from detection.composition_root import AgentConfig, build_agent; \
build_agent(AgentConfig(capture_path='/tmp/features.jsonl', \
model_dir='modelos_agente_tcp', model='tcp', broker_host='localhost', \
alert_dir='/tmp/alerts')).run()"

python -m simulation --broker localhost --port 1883 \
  --paquetes 30000 --ataque dos
```

## Ollama

Compose exposes Ollama on host port `11435` by default and containers reach it
at `http://ollama:11434`. The default model is `gemma3:4b` and is stored in the
persistent `ollama-data` volume:

```bash
OLLAMA_MODEL=gemma3:4b docker compose up --build -d
curl http://localhost:11435/api/tags
docker compose exec ollama ollama list
```

Use another model or host port with:

```bash
OLLAMA_MODEL=llama3.2:3b OLLAMA_PORT=11436 \
  docker compose up --build -d
```

The initializer pulls the selected model before `natural-report` and
`report-api` start. If Ollama cannot be reached, detection continues, while a
natural-report request fails explicitly.

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

The API is served by `report-api` on `http://localhost:8000`. It reads the
`/processed/report.json` generated by the ETL and asks Ollama for the
natural-language report:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/reports \
  -H 'Content-Type: application/json' -d '{}'
```

Response shape:

```json
{"report":"## Summary\n..."}
```

The request body is optional. It can specify a model and a timezone-aware UTC
reference timestamp:

```bash
curl -X POST http://localhost:8000/api/v1/reports \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma3:4b","now":"2026-11-07T12:00:00Z"}'
```

The API returns `404` when summaries are unavailable, `400` for an invalid
timestamp, and `502` when Ollama cannot generate the report.

## Models, data, and limitations

The notebooks live in [`ML_Model/`](ML_Model/):

- `01_eda_politica.ipynb` cleans the data and defines the column policy. The
  task is DoS vs normal; MitM and Intrusion captures contribute only their
  normal traffic.
- `02_tcp_vs_mqtt.ipynb` compares the MQTT feature set with the TCP-only set.
- `03_modelo_tcp.ipynb` trains the TCP model and exports
  [`modelos_agente_tcp/`](modelos_agente_tcp/).

The MQTT artifacts in [`modelos_agente/`](modelos_agente/) come from the earlier
notebook, kept in `ML_Model/backup/`. In every case the feature order is defined
by `pipeline_config.json`; changing features requires retraining and
re-exporting. No model uses raw application payloads as features.

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
