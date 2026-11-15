"""Piezas del agente por separado: claves, cooldown, alerta, ventanas y evidencia."""

import unittest

from detection.application.services import EvidenceBuffer, SlidingWindows
from detection.domain import (
    AlertCooldown,
    FrameContext,
    build_alert,
    connection_key,
    direction_key,
)


def ctx(ts=1.0, src=('10.0.0.5', 40000), dst=('10.0.0.1', 1883), stream=7, client=None):
    return FrameContext(
        ts=ts,
        ip=src[0],
        srcport=src[1],
        dst_ip=dst[0],
        dstport=dst[1],
        stream_id=stream,
        client_id=client,
        tenant_id='t1',
        broker_id='b1',
        sensor_id='s1',
    )


def reply(ts=1.0, **kwargs):
    """Mismo flujo, sentido broker -> cliente."""
    return ctx(ts, src=('10.0.0.1', 1883), dst=('10.0.0.5', 40000), **kwargs)


class FlowKeyTests(unittest.TestCase):
    def test_connection_key_is_shared_by_both_directions(self):
        self.assertEqual(connection_key(ctx()), connection_key(reply()))
        self.assertNotEqual(connection_key(ctx()), connection_key(ctx(stream=8)))

    def test_direction_key_separates_directions_and_needs_endpoints(self):
        self.assertNotEqual(direction_key(ctx()), direction_key(reply()))
        self.assertIsNone(direction_key(FrameContext(ip='10.0.0.5', srcport=1)))


class AlertCooldownTests(unittest.TestCase):
    def test_suppresses_same_label_on_same_connection(self):
        cooldown = AlertCooldown(5.0)
        self.assertFalse(cooldown.should_suppress('ataque', ctx(1.0)))
        self.assertTrue(cooldown.should_suppress('ataque', reply(3.0)))
        self.assertFalse(cooldown.should_suppress('otro', ctx(3.0)))
        self.assertFalse(cooldown.should_suppress('ataque', ctx(6.5)))

    def test_one_more_alert_once_client_id_is_known(self):
        cooldown = AlertCooldown(5.0)
        self.assertFalse(cooldown.should_suppress('ataque', ctx(1.0)))
        self.assertFalse(cooldown.should_suppress('ataque', ctx(2.0, client='dev-1')))
        self.assertTrue(cooldown.should_suppress('ataque', ctx(3.0, client='dev-1')))

    def test_disabled_or_without_timestamp(self):
        self.assertFalse(AlertCooldown(0).should_suppress('a', ctx()))
        cooldown = AlertCooldown(5.0)
        cooldown.should_suppress('a', ctx(None))
        self.assertFalse(cooldown.should_suppress('a', ctx(None)))

    def test_memory_is_bounded(self):
        cooldown = AlertCooldown(5.0, max_tracked=2)
        for stream in range(3):
            cooldown.should_suppress('a', ctx(stream=stream))
        self.assertFalse(cooldown.should_suppress('a', ctx(stream=0)))


class BuildAlertTests(unittest.TestCase):
    def test_reports_client_even_on_broker_reply(self):
        alert = build_alert('ataque', reply(), source='x', server_ports={1883})
        self.assertEqual(alert.ip, '10.0.0.5')
        self.assertEqual(
            build_alert('ataque', ctx(), source='x', server_ports={1883}).ip, '10.0.0.5'
        )
        self.assertEqual((alert.broker_id, alert.source, alert.kind), ('b1', 'x', 'class'))
        self.assertTrue(alert.alert_id)

    def test_missing_timestamp_is_zero(self):
        self.assertEqual(build_alert('a', ctx(None), source='x').ts, 0.0)


class SlidingWindowsTests(unittest.TestCase):
    def test_per_flow_windows_fill_independently(self):
        windows = SlidingWindows(2)
        self.assertIsNone(windows.push(ctx(), {'n': 1}))
        self.assertIsNone(windows.push(reply(), {'n': 2}))
        self.assertEqual(windows.push(ctx(), {'n': 3}), [{'n': 1}, {'n': 3}])
        self.assertEqual(windows.push(ctx(), {'n': 4}), [{'n': 3}, {'n': 4}])

    def test_incomplete_endpoints_are_rejected_only_per_flow(self):
        partial = FrameContext(ip='10.0.0.5')
        self.assertFalse(SlidingWindows(1).accepts(partial))
        self.assertIsNone(SlidingWindows(1).push(partial, {}))
        self.assertTrue(SlidingWindows(1, per_flow=False).accepts(partial))

    def test_global_window_mixes_flows(self):
        windows = SlidingWindows(2, per_flow=False)
        windows.push(ctx(), {'n': 1})
        self.assertEqual(windows.push(reply(), {'n': 2}), [{'n': 1}, {'n': 2}])


class RecordingSink:
    def __init__(self):
        self.writes = []

    def write(self, alert, key, records):
        self.writes.append((alert, key, list(records)))


class EvidenceBufferTests(unittest.TestCase):
    def test_flush_writes_recent_frames_of_both_directions(self):
        sink = RecordingSink()
        evidence = EvidenceBuffer(sink, seconds=10)
        evidence.remember(ctx(1.0), {'n': 'viejo'})
        evidence.remember(reply(15.0), {'n': 'respuesta'})
        evidence.remember(ctx(20.0), {'n': 'actual'})
        alert = build_alert('ataque', ctx(20.0), source='x')
        evidence.flush(alert, ctx(20.0))
        ((written, key, records),) = sink.writes
        self.assertIs(written, alert)
        self.assertEqual(key, connection_key(ctx()))
        self.assertEqual(records, [{'n': 'respuesta'}, {'n': 'actual'}])

    def test_without_sink_or_record_nothing_is_kept(self):
        evidence = EvidenceBuffer(None, seconds=10)
        evidence.remember(ctx(), {'n': 1})
        evidence.flush(build_alert('a', ctx(), source='x'), ctx())  # no falla
        sink = RecordingSink()
        evidence = EvidenceBuffer(sink, seconds=10)
        evidence.remember(ctx(), None)
        evidence.flush(build_alert('a', ctx(), source='x'), ctx())
        self.assertEqual(sink.writes, [])

    def test_memory_is_bounded(self):
        sink = RecordingSink()
        evidence = EvidenceBuffer(sink, seconds=100, max_flows=1, max_records=2)
        for n in range(3):
            evidence.remember(ctx(1.0 + n), {'n': n})
        evidence.remember(ctx(stream=99), {'n': 'otra'})  # expulsa la conexión 7
        evidence.flush(build_alert('a', ctx(5.0), source='x'), ctx(5.0))
        self.assertEqual(sink.writes, [])
        evidence.flush(build_alert('a', ctx(stream=99), source='x'), ctx(stream=99))
        self.assertEqual(sink.writes[0][2], [{'n': 'otra'}])


if __name__ == '__main__':
    unittest.main()
