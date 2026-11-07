# Mosquitto broker configuration

This directory contains the broker configuration used by
[`docker-compose.yml`](../docker-compose.yml). It is configuration, not Python
application code.

## `config/mosquitto.conf`

| Directive | Value | Purpose |
|---|---|---|
| `persistence false` | — | Sessions are not retained between restarts. |
| `allow_anonymous true` | — | Required by the simulator's intrusion scenario. |
| `log_dest file` | `/mosquitto/log/mosquitto.log` | Writes a persistent debug log. |
| `log_dest stdout` | — | Also sends logs to the container output. |
| `log_type all` | — | Logs connections and publications. |
| `log_timestamp true` | — | Adds timestamps to log lines. |
| `listener 1883` | Plaintext | MQTT traffic without encryption. |
| `listener 8883` | TLS | MQTT over TLS using the generated certificate. |
| `max_queued_messages 0` | Unlimited | No queue limit for the lab workload. |
| `message_size_limit 0` | Unlimited | No payload-size limit for the lab workload. |

The anonymous, unrestricted configuration is intended for local testing only.
Do not expose it to an untrusted network.

## Certificates and logs

The `certgen` Compose service creates `server.crt`, `server.key`, and `ca.crt`
with OpenSSL. The certificate is self-signed and includes
`mosquitto`, `localhost`, and `127.0.0.1` as SANs. The broker waits up to 60
seconds for the certificate files before starting.

`certgen` is intentionally not a `depends_on` dependency of Mosquitto because
Podman Compose may translate that relationship into a requirement on an already
exited container. The broker performs its own readiness wait instead.

Certificates and logs are runtime artifacts ignored by Git. The agent does not
consume the Mosquitto log; it is available for troubleshooting and inspection.
