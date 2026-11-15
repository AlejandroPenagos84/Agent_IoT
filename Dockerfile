ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
WORKDIR /app

# Install minimal system dependencies for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

# Upgrade pip and install Python dependencies
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /app/requirements.txt

# Código de la app, modelos exportados y el simulador del laboratorio.
COPY src /app/src
COPY modelos_agente_tcp /app/modelos_agente_tcp
COPY simulation /app/simulation

EXPOSE 8000 8443
# API (auth + detección) y agente en un solo proceso.
CMD ["python", "-m", "app"]
