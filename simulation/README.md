# MQTT/IoT simulation

The simulator publishes normal and controlled laboratory attack traffic to
Mosquitto. Capture, feature extraction, and detection are outside this package.

```bash
python -m simulation --broker localhost --port 1883 \
  --paquetes 500 --ataque todos --verbose
python -m simulation --dry-run --ataque todos --force-attack
```

## Scenarios and timing

Supported scenarios are `none`, `dos`, `mitm`, `intrusion`, and `todos`.
`todos` runs `dos`, `mitm`, and `intrusion` in order. It requires
`--paquetes >= 3 * --burst-size + 2`, because two normal publications are
reserved for intrusion discovery. `--paquetes` counts MQTT publications, not
TCP frames or alerts.

```bash
python -m simulation --broker localhost --ataque todos --paquetes 500 \
  --burst-size 100 --dos-rate 100 --attack-rate 10 --attack-gap 5 \
  --force-attack --seed 42 --verbose
```

The scheduler uses `time.monotonic()`. `--intervalo` is the scheduler pause,
not a clock multiplier. `--dos-rate` and `--attack-rate` are publications per
second during bursts; operating-system delays can reduce the observed rate.
Normal traffic pauses during bursts. `--dry-run` uses virtual time and never
connects to the broker.

## Scenario behavior

Normal devices publish numeric readings to `distance/ultrasonic1` and `0`/`1`
values to `light/rele1`, matching topics in the local CSV data.

- `dos` publishes from multiple clients to `mqtt-malaria/.../data/...`.
  `--dos-clients` defaults to 5, `--dos-payload-size` to 100 bytes, and
  `--dos-rate` controls the rate. Generating load alone does not prove a DoS.
- `mitm` sends `100` through a local TCP proxy that changes the PUBLISH value
  to `900` while preserving length and framing. It does not perform ARP
  spoofing and requires plaintext MQTT.
- `intrusion` subscribes anonymously to `#`, discovers observed topics, and
  publishes forged values. `--discovery-seconds` controls the discovery wait.
  The broker configuration determines whether anonymous access is allowed.

Scenario names are not ML ground truth. The simulator creates traffic; `tshark`
extracts wire features and the classifier produces the final label. Different
rates, clients, topology, or message distributions can produce different
classifications.

The publisher waits for CONNACK, checks publish return codes, and drains
pending messages before disconnecting. QoS 0 completion does not prove ACL
acceptance or consumer delivery.

## Command-line options

The main options are `--broker`, `--port`, `--tls`, `--ca-certs`, `--paquetes`,
`--ataque`, `--intervalo`, `--usuario`, `--usuario-ataque`, `--password`,
`--force-attack`, `--burst-size`, `--dos-rate`, `--attack-rate`, `--attack-gap`,
`--seed`, `--dos-clients`, `--dos-payload-size`, `--discovery-seconds`,
`--verbose`, `--debug`, and `--dry-run`.

TLS uses port `8883` and the generated CA certificate. MitM and `todos` reject
TLS because the laboratory proxy must inspect the MQTT stream.

## Implementation

| Module | Responsibility |
|---|---|
| `devices.py` | Device definitions, topics, payloads, and intervals. |
| `publishers.py` | Publisher port and MQTT/no-op implementations. |
| `attacks.py` | Immutable attack packet descriptions and scenario builders. |
| `mqtt_proxy.py` | TCP PUBLISH transformer, handler, server, and proxy. |
| `simulator.py` | Scheduling, publisher caching, bursts, logging, and shutdown. |
| `cli.py` | Argument parsing and process entry point. |
| `__main__.py` | Enables `python -m simulation`. |

`simulador_iot.py` remains a backward-compatible wrapper. Docker runs
`python -m simulation` directly.

Run tests with:

```bash
python -m unittest discover -s tests -v
```
