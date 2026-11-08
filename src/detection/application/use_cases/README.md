# Agent use case

`Agent` consumes `Frame` values through the `FeatureSource` port, maintains
11-row windows, and emits the latest non-`normal` classification through the
`AlertSink` port. It depends only on application ports and shared types.

By default, buffers are separated by connection and direction using
`(stream_id, ip, srcport, dst_ip, dstport)`. `stream_id` is `tcp.stream` and
prevents connections that reuse endpoints in one capture from being mixed.
Broker responses to different clients are not combined. Set `per_flow=False`
to use one global window.

Classifiers return one label per evaluable frame. The agent uses the last label,
which belongs to the newest frame in the window, and preserves that frame's
context in the alert. LSTM classifiers also evaluate the last complete
sequence. An alert for broker-to-client traffic keeps the broker's source IP;
`ip` identifies the frame source, not necessarily an attacker.

Run regression tests with:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
