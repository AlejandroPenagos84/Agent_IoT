#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

echo "==> Construyendo y levantando la plataforma..."
docker compose up --build -d

echo "==> Esperando a que el simulador termine..."
docker compose wait simulador

echo "==> Deteniendo captura y agente para cerrar los archivos..."
docker compose stop agente capture >/dev/null

echo "==> Normalizando alertas..."
docker compose --profile etl run --rm normalize

echo "==> Generando resúmenes..."
docker compose --profile etl run --rm summaries

echo "==> Generando reportes JSON y natural con Ollama..."
docker compose --profile etl run --rm report

echo
echo "==> Reporte final:"
docker compose --profile etl run --rm \
  --entrypoint sh report -c 'cat /processed/report.md'
