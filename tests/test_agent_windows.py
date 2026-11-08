import unittest

from application.ports.ports_out import AlertSink, Classifier, FeatureSource
from application.ports.types import Frame
from application.use_cases.agent import Agent
from domain.model import FrameContext
from infrastructure.classifiers._common import crear_secuencias
from infrastructure.tshark.stream_features import FIELDS, record_from_fields
from infrastructure.tshark.tshark_feature_source import TsharkFeatureSource


class Source(FeatureSource):
    def __init__(self, frames):
        self.frames = frames

    def start(self):
        pass

    def rows(self):
        yield from self.frames


class Recorder(Classifier):
    def __init__(self):
        self.windows = []

    def predict(self, window):
        self.windows.append(window)
        return ['ataque']


class Sink(AlertSink):
    def __init__(self):
        self.alerts = []

    def emit(self, alert):
        self.alerts.append(alert)


def frame(client, index, stream=1, reverse=False):
    src, dst = ('broker', client) if not reverse else (client, 'broker')
    sport, dport = (1883, 40000) if not reverse else (40000, 1883)
    return Frame({'marker': index}, FrameContext(
        ts=float(index), ip=src, dst_ip=dst, srcport=sport, dstport=dport,
        stream_id=stream, topic=f'topic/{index}'))


class WindowTests(unittest.TestCase):
    def run_agent(self, frames, **kwargs):
        classifier, sink = Recorder(), Sink()
        Agent(Source(frames), classifier, sink, **kwargs).run()
        return classifier, sink

    def test_broker_responses_to_different_ips_do_not_mix(self):
        frames = [f for i in range(11)
                  for f in (frame('a', i), frame('b', i))]
        classifier, sink = self.run_agent(frames)
        self.assertEqual(len(classifier.windows), 2)
        self.assertEqual(len(sink.alerts), 2)

    def test_directions_and_reused_connections_do_not_mix(self):
        frames = [f for i in range(6) for f in (
            frame('a', i), frame('a', i, reverse=True),
            frame('a', i, stream=2))]
        classifier, sink = self.run_agent(frames)
        self.assertEqual(classifier.windows, [])
        self.assertEqual(sink.alerts, [])

    def test_incomplete_endpoints_are_skipped(self):
        frames = [Frame({}, FrameContext(ip='broker', srcport=1883))] * 11
        classifier, _ = self.run_agent(frames)
        self.assertEqual(classifier.windows, [])

    def test_alert_context_matches_last_frame_in_both_modes(self):
        for per_flow in (True, False):
            with self.subTest(per_flow=per_flow):
                classifier, sink = self.run_agent(
                    [frame('a', i) for i in range(11)], per_flow=per_flow)
                self.assertEqual(classifier.windows[-1][-1]['marker'], 10)
                self.assertEqual(sink.alerts[-1].ts, 10)
                self.assertEqual(sink.alerts[-1].topic, 'topic/10')

    def test_capture_context_is_not_a_model_feature(self):
        values = {'ip.src': 'broker', 'ip.dst': 'a', 'tcp.srcport': '1883',
                  'tcp.dstport': '40000', 'tcp.stream': '7'}
        record = record_from_fields([values.get(field, '') for field in FIELDS])
        source = TsharkFeatureSource()
        context = source._context(record)
        self.assertEqual(context.dst_ip, 'a')
        self.assertEqual(context.stream_id, 7)
        self.assertNotIn('ip.dst', source._features(record))
        self.assertNotIn('tcp.stream', source._features(record))

    def test_lstm_last_prediction_uses_last_frame(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy no instalado')
        for size, count in ((9, 0), (10, 1), (11, 2), (15, 6)):
            with self.subTest(size=size):
                xs, ends = crear_secuencias(np.arange(size).reshape(-1, 1))
                self.assertEqual(len(xs), count)
                if count:
                    self.assertEqual(ends[-1], size - 1)
                    self.assertEqual(xs[-1, -1, 0], size - 1)


def record(values):
    return record_from_fields([values.get(field, '') for field in FIELDS])


class FlowContextTests(unittest.TestCase):
    def setUp(self):
        self.source = TsharkFeatureSource()

    def test_connect_client_id_and_topic_are_remembered(self):
        self.source._context(record({'tcp.stream': '7', 'mqtt.msgtype': '1',
                                     'mqtt.clientid': 'sensor1'}))
        publish = self.source._context(record({'tcp.stream': '7', 'mqtt.msgtype': '3',
                                               'mqtt.topic': 'home/temp'}))
        self.assertEqual(publish.client_id, 'sensor1')
        self.assertEqual(publish.topic, 'home/temp')
        ack = self.source._context(record({'tcp.stream': '7', 'mqtt.msgtype': '3'}))
        self.assertEqual(ack.client_id, 'sensor1')
        self.assertEqual(ack.topic, 'home/temp')

    def test_streams_do_not_share_state(self):
        self.source._context(record({'tcp.stream': '1', 'mqtt.clientid': 'a',
                                     'mqtt.topic': 't/a'}))
        self.source._context(record({'tcp.stream': '2', 'mqtt.clientid': 'b'}))
        second = self.source._context(record({'tcp.stream': '2'}))
        self.assertEqual(second.client_id, 'b')
        self.assertIsNone(second.topic)

    def test_missing_stream_does_not_remember(self):
        connect = self.source._context(record({'mqtt.clientid': 'x', 'mqtt.topic': 't/x'}))
        self.assertEqual(connect.client_id, 'x')
        self.assertEqual(connect.topic, 't/x')
        later = self.source._context(record({'mqtt.msgtype': '3'}))
        self.assertIsNone(later.client_id)
        self.assertIsNone(later.topic)

    def test_start_clears_flow_state(self):
        self.source._context(record({'tcp.stream': '7', 'mqtt.clientid': 'sensor1'}))
        self.source.start()
        after = self.source._context(record({'tcp.stream': '7'}))
        self.assertIsNone(after.client_id)
