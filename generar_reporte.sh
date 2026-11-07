#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")"

echo "==> Construyendo y levantando la plataforma..."
docker compose up --build -d

echo "==> Esperando a que el simulador termine..."
docker compose wait simulador

echo "==> Deteniendo ETL, captura y agente para cerrar los archivos..."
docker compose stop etl agente capture >/dev/null

echo "==> Normalizando alertas..."
docker compose --profile etl run --rm normalize

echo "==> Generando resúmenes..."
docker compose --profile etl run --rm summaries

echo "==> Generando reporte JSON..."
docker compose --profile etl run --rm report

echo "==> Generando reporte natural con Ollama..."
docker compose --profile etl run --rm natural-report

echo
echo "==> Reporte final:"
docker compose --profile etl run --rm natural-report
