"""Fase 0: admisión TCP/L2, normalización MAC, límites de episodio y contexto.

Estas comprobaciones son estáticas de contrato: verifican la lógica de la fuente
y del agente sobre frames construidos a mano. No inician tshark ni ejecutan
entrenamiento o inferencia.
"""
import math
import unittest

from application.ports.ports_out import AlertSink, Classifier, FeatureSource
from application.ports.types import Frame
from application.use_cases.agent import Agent
from domain.model import FrameContext
from infrastructure.features import ContextFeatureSource
from infrastructure.tshark.stream_features import (
    FIELDS, build_display_filter, record_from_fields,
)
from infrastructure.tshark.tshark_feature_source import TsharkFeatureSource


class Source(FeatureSource):
    def __init__(self, frames):
        self.frames = frames

    def start(self):
        pass

    def rows(self):
        yield from self.frames


class Recorder(Classifier):
    def __init__(self, label='intrusion'):
        self.label = label
        self.windows = []

    def predict(self, window):
        self.windows.append(window)
        return [self.label]


class Sink(AlertSink):
    def __init__(self):
        self.alerts = []

    def emit(self, alert):
        self.alerts.append(alert)


def l2_frame(eth_src, eth_dst, ts):
    return Frame({'frame.time_epoch': ts},
                 FrameContext(ts=ts, eth_src=eth_src, eth_dst=eth_dst))


def tcp_frame(ip, srcport, dst_ip, dstport, ts, stream=1):
    return Frame({'frame.time_epoch': ts},
                 FrameContext(ts=ts, ip=ip, srcport=srcport,
                              dst_ip=dst_ip, dstport=dstport, stream_id=stream))


def run_agent(frames, label='intrusion', **kwargs):
    classifier, sink = Recorder(label), Sink()
    Agent(Source(frames), classifier, sink, **kwargs).run()
    return classifier, sink


def capture(values):
    return record_from_fields([values.get(field, '') for field in FIELDS])


class AdmissionTests(unittest.TestCase):
    def test_l2_without_ip_ports_or_mqtt_is_admitted(self):
        # Ausencia de IP, puertos y MQTT no descarta una trama con MAC y reloj.
        frames = [l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', float(i))
                  for i in range(11)]
        classifier, _ = run_agent(frames)
        self.assertEqual(len(classifier.windows), 1)

    def test_frame_without_endpoints_or_macs_is_skipped(self):
        frames = [Frame({}, FrameContext(ts=float(i))) for i in range(11)]
        classifier, _ = run_agent(frames)
        self.assertEqual(classifier.windows, [])

    def test_missing_port_is_not_completed_to_become_tcp(self):
        # Puerto ausente (0) no se rellena; sin MACs no hay admisión.
        frames = [Frame({}, FrameContext(ts=float(i), ip='a', dst_ip='b',
                                         srcport=0, dstport=1883))
                  for i in range(11)]
        classifier, _ = run_agent(frames)
        self.assertEqual(classifier.windows, [])

    def test_non_finite_clock_is_not_tcp(self):
        frames = [tcp_frame('a', 40000, 'b', 1883, float('nan'))
                  for _ in range(11)]
        classifier, _ = run_agent(frames)
        self.assertEqual(classifier.windows, [])

    def test_tcp_frame_is_admitted(self):
        frames = [tcp_frame('a', 40000, 'b', 1883, float(i)) for i in range(11)]
        classifier, _ = run_agent(frames)
        self.assertEqual(len(classifier.windows), 1)

    def test_source_does_not_complete_missing_dstport(self):
        source = TsharkFeatureSource()
        context = source._context(capture({
            'ip.src': 'a', 'ip.dst': 'b', 'tcp.srcport': '40000',
            'frame.time_epoch': '1.0'}))
        self.assertEqual(context.dstport, 0)


class EpisodeGapTests(unittest.TestCase):
    @staticmethod
    def two_segments(second_start, step=0.5):
        first = [l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb',
                          i * step) for i in range(6)]
        second = [l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb',
                           second_start + i * step) for i in range(6)]
        return first + second

    def test_gap_equal_to_one_second_keeps_episode(self):
        # 6 + 6 frames separados por exactamente 1 s: un solo episodio -> 2 ventanas.
        classifier, _ = run_agent(self.two_segments(3.5))
        self.assertEqual(len(classifier.windows), 2)

    def test_gap_strictly_greater_than_one_second_starts_episode(self):
        classifier, _ = run_agent(self.two_segments(3.5001))
        self.assertEqual(classifier.windows, [])

    def test_clock_regression_starts_episode(self):
        classifier, _ = run_agent(self.two_segments(-1.0))
        self.assertEqual(classifier.windows, [])


class MacNormalizationTests(unittest.TestCase):
    def test_source_normalizes_mac(self):
        source = TsharkFeatureSource()
        context = source._context(capture({
            'eth.src': ' AA:BB:CC:DD:EE:FF ',
            'eth.dst': 'FF:FF:FF:FF:FF:FF',
        }))
        self.assertEqual(context.eth_src, 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(context.eth_dst, 'ff:ff:ff:ff:ff:ff')

    def test_whitespace_only_mac_is_absent(self):
        source = TsharkFeatureSource()
        context = source._context(capture({'eth.src': '   '}))
        self.assertIsNone(context.eth_src)

    def test_agent_groups_mac_case_variants(self):
        variants = ['AA:BB:CC:DD:EE:FF', ' aa:bb:cc:dd:ee:ff ']
        frames = [l2_frame(variants[i % 2], '11:22:33:44:55:66', float(i))
                  for i in range(11)]
        classifier, _ = run_agent(frames)
        self.assertEqual(len(classifier.windows), 1)


class ContextFeatureTests(unittest.TestCase):
    def collect(self, frames):
        builder = ContextFeatureSource(Source(frames))
        builder.start()
        return list(builder.rows())

    def test_broadcast_is_case_insensitive(self):
        rows = self.collect([
            l2_frame('aa:aa:aa:aa:aa:aa', ' FF:FF:FF:FF:FF:FF ', 0.0)])
        self.assertEqual(rows[0].features['_ctx_is_broadcast'], 1.0)

    def test_originless_l2_keeps_nan_origin_rates(self):
        rows = self.collect([
            l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 0.0)])
        self.assertTrue(math.isnan(rows[0].features['_ctx_origen_frames_s']))

    def test_l2_rates_are_nan_without_eth_src(self):
        rows = self.collect([l2_frame(None, 'ff:ff:ff:ff:ff:ff', 0.0)])
        self.assertTrue(math.isnan(rows[0].features['_ctx_l2_frames_s']))


class AlertTopicExclusionTests(unittest.TestCase):
    def test_exclusion_is_negated_equality_not_presence(self):
        # `!(mqtt.topic == ...)` deja pasar las tramas que no traen el topic.
        self.assertEqual(build_display_filter('', 'alertas/deteccion'),
                         '!(mqtt.topic == "alertas/deteccion")')

    def test_exclusion_keeps_base_filter(self):
        self.assertEqual(build_display_filter('mqtt', 'alertas/deteccion'),
                         '(mqtt) && !(mqtt.topic == "alertas/deteccion")')

    def test_no_exclusion_is_empty(self):
        self.assertEqual(build_display_filter('', None), '')

    def test_non_mqtt_frame_yields_features_and_context(self):
        source = TsharkFeatureSource()
        record = capture({'eth.src': 'aa:bb:cc:dd:ee:ff',
                          'eth.dst': 'ff:ff:ff:ff:ff:ff',
                          'frame.time_epoch': '1.0'})
        self.assertNotIn('ip.src', source._features(record))
        self.assertEqual(source._context(record).eth_src, 'aa:bb:cc:dd:ee:ff')


class L2DoesNotAssignAttackTests(unittest.TestCase):
    def test_normal_l2_frames_emit_no_alert(self):
        frames = [l2_frame('aa:aa:aa:aa:aa:aa', 'ff:ff:ff:ff:ff:ff', float(i))
                  for i in range(11)]
        _, sink = run_agent(frames, label='normal')
        self.assertEqual(sink.alerts, [])

    def test_emitted_label_equals_classifier_output(self):
        frames = [l2_frame('aa:aa:aa:aa:aa:aa', 'ff:ff:ff:ff:ff:ff', float(i))
                  for i in range(11)]
        _, sink = run_agent(frames, label='mitm')
        self.assertEqual([alert.label for alert in sink.alerts], ['mitm'])
        self.assertIsNone(sink.alerts[-1].mse)


if __name__ == '__main__':
    unittest.main()
