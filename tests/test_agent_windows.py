import unittest

from detection.application.ports.ports_out import AlertSink, Classifier, FeatureSource
from detection.application.ports.types import Frame
from detection.application.use_cases.agent import Agent
from detection.domain.model import FrameContext
from detection.infrastructure.tshark.record_parser import RecordParser
from detection.infrastructure.tshark.stream_features import CAPTURE_FIELDS, record_from_fields


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


def frame(client, index, stream=1, reverse=False, sensor='s1'):
    src, dst = ('broker', client) if not reverse else (client, 'broker')
    sport, dport = (1883, 40000) if not reverse else (40000, 1883)
    return Frame({'marker': index}, FrameContext(
        ts=float(index), ip=src, dst_ip=dst, srcport=sport, dstport=dport,
        stream_id=stream, topic=f'topic/{index}', tenant_id='t',
        broker_id='b', sensor_id=sensor))


def record(values):
    data = record_from_fields([values.get(field, '') for field in CAPTURE_FIELDS])
    data.update({key: value for key, value in values.items()
                 if key not in CAPTURE_FIELDS})
    return data


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

    def test_same_stream_on_different_sensors_does_not_mix(self):
        frames = [f for i in range(11)
                  for f in (frame('a', i, sensor='s1'),
                            frame('a', i, sensor='s2'))]
        classifier, sink = self.run_agent(frames)
        self.assertEqual(len(classifier.windows), 2)
        self.assertEqual({alert.sensor_id for alert in sink.alerts},
                         {'s1', 's2'})

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
        parser = RecordParser()
        parsed = record(values)
        context = parser.context(parsed)
        self.assertEqual(context.dst_ip, 'a')
        self.assertEqual(context.stream_id, 7)
        self.assertIsNone(parser.features(parsed))


class FlowContextTests(unittest.TestCase):
    def setUp(self):
        self.parser = RecordParser()

    def test_connect_client_id_and_topic_are_remembered(self):
        self.parser.context(record({'tcp.stream': '7', 'mqtt.msgtype': '1',
                                    'mqtt.clientid': 'sensor1'}))
        publish = self.parser.context(record({'tcp.stream': '7', 'mqtt.msgtype': '3',
                                              'mqtt.topic': 'home/temp'}))
        self.assertEqual(publish.client_id, 'sensor1')
        self.assertEqual(publish.topic, 'home/temp')
        ack = self.parser.context(record({'tcp.stream': '7', 'mqtt.msgtype': '3'}))
        self.assertEqual(ack.client_id, 'sensor1')
        self.assertEqual(ack.topic, 'home/temp')

    def test_streams_do_not_share_state(self):
        self.parser.context(record({'tcp.stream': '1', 'mqtt.clientid': 'a',
                                    'mqtt.topic': 't/a'}))
        self.parser.context(record({'tcp.stream': '2', 'mqtt.clientid': 'b'}))
        second = self.parser.context(record({'tcp.stream': '2'}))
        self.assertEqual(second.client_id, 'b')
        self.assertIsNone(second.topic)

    def test_missing_stream_does_not_remember(self):
        connect = self.parser.context(record({'mqtt.clientid': 'x', 'mqtt.topic': 't/x'}))
        self.assertEqual(connect.client_id, 'x')
        self.assertEqual(connect.topic, 't/x')
        later = self.parser.context(record({'mqtt.msgtype': '3'}))
        self.assertIsNone(later.client_id)
        self.assertIsNone(later.topic)

    def test_reset_clears_flow_state(self):
        self.parser.context(record({'tcp.stream': '7', 'mqtt.clientid': 'sensor1'}))
        self.parser.reset()
        after = self.parser.context(record({'tcp.stream': '7'}))
        self.assertIsNone(after.client_id)

    def test_streams_are_isolated_by_sensor(self):
        base = {'tenant_id': 't', 'broker_id': 'b', 'tcp.stream': '7'}
        self.parser.context(record({**base, 'sensor_id': 's1',
                                    'mqtt.clientid': 'a'}))
        other = self.parser.context(record({**base, 'sensor_id': 's2'}))
        self.assertIsNone(other.client_id)
