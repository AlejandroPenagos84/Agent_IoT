from pathlib import Path
import importlib.util
import unittest

from detection.application.ports.ports_out import AlertSink, Classifier, FeatureSource
from detection.application.ports.types import Frame
from detection.application.use_cases.agent import Agent
from detection.domain.model import FrameContext
from detection.infrastructure.tshark.record_parser import RecordParser
from detection.infrastructure.tshark.tcp_window_features import TCP_FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'modelos_agente_tcp'
HAS_XGB = all(importlib.util.find_spec(m) for m in ('xgboost', 'pandas', 'joblib'))


class Source(FeatureSource):
    def __init__(self, frames):
        self.frames = frames

    def start(self):
        pass

    def rows(self):
        yield from self.frames


class AlwaysAttack(Classifier):
    def predict(self, window):
        return ['ataque'] * len(window)


class Sink(AlertSink):
    def __init__(self):
        self.alerts = []

    def emit(self, alert):
        self.alerts.append(alert)


def context(ts, port=40000):
    return FrameContext(ts=ts, ip='10.0.0.1', dst_ip='10.0.0.2', srcport=port,
                        dstport=1883, stream_id=port)


class TcpAgentTests(unittest.TestCase):
    def test_parser_yields_precomputed_features_and_keeps_connect_context(self):
        features = dict.fromkeys(TCP_FEATURE_COLUMNS, 1.0)
        parser = RecordParser()
        connect = {'mqtt.clientid': 'c1', 'tcp.stream': 3, 'ip.src': '10.0.0.1',
                   'tcp.srcport': 40000, 'ip.dst': '10.0.0.2', 'tcp.dstport': 1883}
        publish = {'tcp.stream': 3, 'ip.src': '10.0.0.1', 'tcp.srcport': 40000,
                   'ip.dst': '10.0.0.2', 'tcp.dstport': 1883,
                   'tcp_features': features}
        self.assertIsNone(parser.features(connect))
        parser.context(connect)
        self.assertEqual(parser.features(publish), features)
        self.assertEqual(parser.context(publish).client_id, 'c1')

    def test_cooldown_limits_alerts_per_flow(self):
        frames = [Frame({}, context(t)) for t in (0.0, 1.0, 4.9, 5.0, 9.0)]
        frames.append(Frame({}, context(1.0, port=40001)))
        sink = Sink()
        Agent(Source(frames), AlwaysAttack(), sink, window_size=1,
              alert_cooldown=5.0).run()
        self.assertEqual([a.ts for a in sink.alerts], [0.0, 5.0, 1.0])

    def test_cooldown_is_per_connection_and_upgrades_once_with_client_id(self):
        known = FrameContext(ts=2.0, ip='10.0.0.1', dst_ip='10.0.0.2', srcport=40000,
                             dstport=1883, stream_id=40000, client_id='c1')
        reply = FrameContext(ts=1.0, ip='10.0.0.2', dst_ip='10.0.0.1', srcport=1883,
                             dstport=40000, stream_id=40000)
        frames = [Frame({}, context(0.0)), Frame({}, reply), Frame({}, known),
                  Frame({}, known)]
        sink = Sink()
        Agent(Source(frames), AlwaysAttack(), sink, window_size=1, alert_cooldown=5.0,
              server_ports=(1883,)).run()
        self.assertEqual([(a.client_id, a.ip) for a in sink.alerts],
                         [(None, '10.0.0.1'), ('c1', '10.0.0.1')])

    def test_broker_reply_reports_client_ip(self):
        reply = FrameContext(ts=1.0, ip='10.0.0.2', dst_ip='10.0.0.1', srcport=1883,
                             dstport=40000, stream_id=1)
        sink = Sink()
        Agent(Source([Frame({}, reply)]), AlwaysAttack(), sink, window_size=1,
              server_ports=(1883,)).run()
        self.assertEqual(sink.alerts[0].ip, '10.0.0.1')

    def test_without_cooldown_every_window_alerts(self):
        sink = Sink()
        frames = [Frame({}, context(t)) for t in (0.0, 1.0, 2.0)]
        Agent(Source(frames), AlwaysAttack(), sink, window_size=1).run()
        self.assertEqual(len(sink.alerts), 3)

    @unittest.skipUnless(HAS_XGB and (MODEL_DIR / 'xgb_tcp.ubj').is_file(),
                         'requiere xgboost y modelos_agente_tcp/')
    def test_classifier_loads_export_and_labels_rows(self):
        from detection.infrastructure.classifiers import TcpXgbClassifier

        classifier = TcpXgbClassifier(str(MODEL_DIR))
        quiet = dict.fromkeys(TCP_FEATURE_COLUMNS, 0.0)
        quiet.update({'frame.len': 66.0, 'fe_log_len': 4.2, 'frame.time_delta': 0.5,
                      'fe_is_standard_mqtt_port': 1.0, 'tcp_iat': 2.0})
        flood = dict(quiet, **{'frame.len': 1514.0, 'fe_log_len': 7.32,
                               'frame.time_delta': 0.0001, 'tcp_iat': 0.0,
                               'tcp_frames_5s': 53.0, 'tcp_bytes_5s': 11.2,
                               'tcp_len_std_5s': 360.0, 'tcp_asymmetry_5s': 0.92,
                               'tcp_new_conns_5s': 120.0})
        self.assertEqual(classifier.predict([quiet, flood]), ['normal', 'ataque'])
        with self.assertRaisesRegex(ValueError, 'faltan features TCP'):
            classifier.predict([{'frame.len': 1.0}])


if __name__ == '__main__':
    unittest.main()
