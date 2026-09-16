ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# If you need a CUDA-enabled PyTorch image, build with:
# docker build --build-arg BASE_IMAGE=pytorch/pytorch:2.14.0-cuda13.0-cudnn8-runtime -t proyecto:latest .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
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

# Copy project files
COPY . /app

# Run the simulator by default. Arguments can be overridden at run time.
ENTRYPOINT ["python", "/app/simulador_iot.py"]
CMD ["--broker", "mosquitto", "--port", "1883", "--ataque", "todos", "--paquetes", "60"]
