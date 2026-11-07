# `tshark` adapters

`stream_features.py` is the capture sidecar. It runs `tshark`, coerces the
selected fields, and appends one JSON record per frame.

`tshark_feature_source.py` implements the application `FeatureSource` port. It
tails the JSONL file, handles partial lines, and converts records into frame
context and model features.

`tshark_schema.py` defines the canonical network column order shared by capture,
frame conversion, and classifiers.

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
python -m infrastructure.tshark.stream_features \
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
