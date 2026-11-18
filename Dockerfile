ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src
WORKDIR /app

# Todas las dependencias tienen wheels: sin compiladores, git ni curl.
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Código de la app, modelo exportado y el simulador del laboratorio.
COPY src /app/src
COPY modelos_agente_tcp /app/modelos_agente_tcp
COPY simulation /app/simulation

EXPOSE 8000 8443
# API (auth + detección) y agente en un solo proceso.
CMD ["python", "-m", "app"]
