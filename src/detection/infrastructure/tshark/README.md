# `tshark` adapters

`stream_features.py` is the capture sidecar. It runs `tshark`, coerces the
selected fields, and appends one JSON record per frame.

`tshark_feature_source.py` implements the application `FeatureSource` port. It
tails the JSONL file, handles partial lines, and converts records into frame
context and model features.

`tshark_schema.py` defines the canonical network column order shared by capture,
frame conversion, and classifiers.

`tcp_window_features.py` (`TcpWindowFeatures`) calcula en línea las 12 features TCP
del modelo B y `stream_features.py` las guarda en cada registro como
`tcp_features` (dict en el orden de `TCP_FEATURE_COLUMNS`). Es el espejo incremental
de `ML_Model/data_preprocessing/tcp_features.py`: mismas ventanas causales de 5 s y
mismas claves de conexión (endpoints + nº de CONNECT) y dirección.
`tests/test_tcp_window_features.py` comprueba que coincide exactamente con la matriz
de entrenamiento sobre `DoS.csv`. Como el modelo se entrenó con la vista `mqtt`,
`tcp_features` es `null` en frames sin puerto 1883/8883, y esos frames tampoco entran
en las ventanas. Solo usa la biblioteca estándar.

`Dockerfile.capture` empaqueta únicamente los módulos del recolector y su
schema, además de los `__init__.py`. No necesita `application`, `domain` ni
dependencias ML. El paquete carga `TsharkFeatureSource` de forma lazy solo
cuando se importa explícitamente, para que arrancar el recolector con `python
-m detection.infrastructure.tshark.stream_features` no cargue el agente.

## Container behavior

[`Dockerfile.capture`](../../Dockerfile.capture) packages only the capture
modules and schema. It does not need the application, domain, or ML
dependencies. The sidecar runs in Mosquitto's network namespace with
`NET_RAW` and `NET_ADMIN` capabilities.

Rebuild only the sidecar with:

```bash
docker compose up -d --build --force-recreate capture
```

By default all frames are captured. Use `--filter` to restrict the capture:

```bash
python -m detection.infrastructure.tshark.stream_features \
  --iface eth0 --filter mqtt --exclude-topic alertas/deteccion \
  --out /tmp/features.jsonl
```

Fields unavailable in a particular `tshark` version are written as `null` with
a warning. The capture includes `ip.dst` and `tcp.stream` as connection
context, but those values are not model features.

## Flow context

The agent keeps separate windows for
`(tcp.stream, ip.src, tcp.srcport, ip.dst, tcp.dstport)`. This prevents
responses from different clients or reused ports from being mixed. Each
direction has its own window.

Per-flow mode skips records without complete source and destination endpoint
data. `tcp.stream` is optional for sources that do not provide it. Older
captures without `ip.dst` cannot be used in this mode.

`FrameContext` correlates the client ID from CONNECT frames and the latest topic
by `tcp.stream`. Subsequent frames inherit that context when their own fields
are absent. State resets at `start()` and when the JSONL input is truncated.
