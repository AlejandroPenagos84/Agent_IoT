# Agent use cases

`Agent` consumes `Frame` values through the `FeatureSource` port, maintains
11-row windows, and emits the latest non-`normal` classification through the
`AlertSink` port. It depends only on application ports and shared types.

`BrokerPool` creates one `Agent` per `(tenant_id, broker_id)`. Each worker has
its own bounded queue, classifier and state. `DetectionServer` starts the
asyncio socket transport and waits until stopped.

Buffers are separated by identity, connection and direction using
`(tenant_id, broker_id, sensor_id, stream_id, ip, srcport, dst_ip, dstport)`.
`stream_id` is `tcp.stream` and prevents connections that reuse endpoints from
being mixed, even across different brokers or sensors. Set `per_flow=False` to
use one global window.

Classifiers return one label per evaluable frame. The agent uses the last label,
which belongs to the newest frame in the window, and preserves that frame's
context in the alert. An alert for broker-to-client traffic keeps the broker's
source IP; `ip` identifies the frame source, not necessarily an attacker.

Run regression tests with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
