"""Fase 4: contrato multiclase, tasa de bytes causal y entropía sobre texto.

Cubre el orden canónico de clases, la normalización/rechazo de etiquetas, la
carga validada del encoder, la tasa causal de bytes por dirección, la
interpretación textual de `mqtt.msg` y la carga del adapter LSTM supervisado.
No entrena ni ejecuta el notebook.
"""
import json
import math
import os
import tempfile
import unittest

from application.ports.ports_out import Classifier, FeatureSource
from application.ports.types import Frame
from domain.model import FrameContext
from infrastructure.features import ContextFeatureSource


def common():
    try:
        from infrastructure.classifiers import _common
    except ImportError:
        raise unittest.SkipTest('dependencias de clasificadores no instaladas')
    return _common


class StubSource(FeatureSource):
    def __init__(self, frames):
        self.frames = frames

    def start(self):
        pass

    def rows(self):
        yield from self.frames


def tcp_frame(ip, epoch, length=60, stream=1, srcport=40000, dstport=1883,
              dst_ip='broker', msgtype=3):
    features = {'frame.time_epoch': epoch, 'mqtt.msgtype': msgtype}
    if length is not None:
        features['frame.len'] = length
    return Frame(features,
                 FrameContext(ts=epoch, ip=ip, srcport=srcport, dst_ip=dst_ip,
                              dstport=dstport, stream_id=stream))


def l2_frame(eth_src, eth_dst, epoch, length=60, ip=None):
    return Frame({'frame.time_epoch': epoch, 'frame.len': length,
                  'mqtt.msgtype': None},
                 FrameContext(ts=epoch, eth_src=eth_src, eth_dst=eth_dst, ip=ip))


class ClassContractTests(unittest.TestCase):
    def test_canonical_order(self):
        self.assertEqual(common().CLASS_NAMES,
                         ['normal', 'DoS', 'mitm', 'intrusion'])

    def test_normalization(self):
        normalize = common().normalize_label
        self.assertEqual(normalize('DoS'), 'DoS')
        self.assertEqual(normalize(' dos '), 'DoS')
        self.assertEqual(normalize('MITM'), 'mitm')
        self.assertEqual(normalize('intrusion'), 'intrusion')
        self.assertEqual(normalize('Normal'), 'normal')

    def test_unknown_label_is_rejected(self):
        with self.assertRaises(ValueError):
            common().normalize_label('ataque')

    def test_class_contract_requires_four_classes(self):
        validate = common().validate_class_contract
        validate({'class_names': common().CLASS_NAMES})
        with self.assertRaises(ValueError):
            validate({'class_names': ['normal', 'ataque']})

    def test_label_encoder_order_is_validated(self):
        try:
            import joblib
            from sklearn.preprocessing import LabelEncoder
        except ImportError:
            raise unittest.SkipTest('joblib/scikit-learn no instalados')
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'le_target.joblib')
            joblib.dump(LabelEncoder().fit(common().CLASS_NAMES), path)
            encoder = common().load_label_encoder(directory, {})
            self.assertEqual(list(encoder.classes_), common().CLASS_NAMES)
            joblib.dump(LabelEncoder().fit(['normal', 'ataque']), path)
            with self.assertRaises(ValueError):
                common().load_label_encoder(directory, {})

    def test_lstm_adapter_is_a_classifier(self):
        from infrastructure.classifiers import LstmClassifier
        self.assertTrue(issubclass(LstmClassifier, Classifier))


class DirectionRateTests(unittest.TestCase):
    def collect(self, frames, window=5.0):
        builder = ContextFeatureSource(StubSource(frames), window_seconds=window)
        builder.start()
        return list(builder.rows())

    def test_no_history_is_zero(self):
        rows = self.collect([tcp_frame('a', 0.0, 60)])
        self.assertEqual(rows[0].features['_ctx_bytes_per_s'], 0.0)

    def test_current_frame_is_excluded(self):
        rows = self.collect([tcp_frame('a', 0.0, 60), tcp_frame('a', 1.0, 100)])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 60 / 5)

    def test_exactly_five_seconds_counts(self):
        rows = self.collect([tcp_frame('a', 0.0, 60), tcp_frame('a', 5.0, 60)])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 60 / 5)

    def test_above_five_seconds_evicts(self):
        rows = self.collect([tcp_frame('a', 0.0, 60), tcp_frame('a', 5.0001, 60)])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 0.0)

    def test_equal_timestamps_count_for_later_frames(self):
        rows = self.collect([tcp_frame('a', 2.0, 60), tcp_frame('a', 2.0, 60)])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 60 / 5)

    def test_clock_rollback_clears_history(self):
        rows = self.collect([tcp_frame('a', 10.0, 60), tcp_frame('a', 5.0, 60)])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 0.0)

    def test_directions_are_isolated(self):
        rows = self.collect([
            tcp_frame('a', 0.0, 60, srcport=40000, dstport=1883),
            tcp_frame('b', 1.0, 100, srcport=1883, dstport=40000),
        ])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 0.0)

    def test_missing_length_does_not_add_bytes(self):
        rows = self.collect([
            tcp_frame('a', 0.0, length=None),
            tcp_frame('a', 1.0, 100),
        ])
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 0.0)

    def test_l2_episode_resets(self):
        same = self.collect([
            l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 0.0),
            l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 0.5),
        ])
        self.assertEqual(same[1].features['_ctx_bytes_per_s'], 60 / 5)
        reset = self.collect([
            l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 0.0),
            l2_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 1.0001 * 2),
        ])
        self.assertEqual(reset[1].features['_ctx_bytes_per_s'], 0.0)

    def test_tcp_without_stream_uses_connect_session(self):
        # Sin tcp.stream, un CONNECT abre sesión nueva (igual que `_connection`).
        rows = self.collect([
            tcp_frame('a', 0.0, 60, stream=None, srcport=1, dstport=1883),
            tcp_frame('a', 0.5, 100, stream=None, srcport=1, dstport=1883,
                      msgtype=1),
            tcp_frame('a', 1.0, 100, stream=None, srcport=1, dstport=1883),
        ])
        self.assertEqual(rows[0].features['_ctx_bytes_per_s'], 0.0)
        self.assertEqual(rows[1].features['_ctx_bytes_per_s'], 0.0)
        # El CONNECT (100 B) sí cuenta para el frame posterior de la nueva sesión.
        self.assertEqual(rows[2].features['_ctx_bytes_per_s'], 100 / 5)


class DirectionRateFeatureTests(unittest.TestCase):
    def test_transport_is_log1p_mapped(self):
        try:
            import numpy as np
            import pandas as pd
        except ImportError:
            raise unittest.SkipTest('numpy/pandas no instalados')
        common_mod = common()
        df = pd.DataFrame({'frame.len': [60.0], 'frame.time_delta': [0.01],
                           '_ctx_bytes_per_s': [np.e - 1.0],
                           'tcp.srcport': [40000.0], 'tcp.dstport': [1883.0]})
        features = common_mod.build_network_features(df)
        self.assertAlmostEqual(float(features['fe_bytes_per_sec'].iloc[0]), 1.0)


class PayloadEntropyTests(unittest.TestCase):
    def test_hex_digit_text_is_not_decoded(self):
        common_mod = common()
        # '48' como texto tiene dos simbolos distintos (1 bit), como bytes seria
        # 'H' (0 bits). La entropia debe calcularse sobre el texto original.
        self.assertEqual(common_mod.entropia('48'), 1.0)

    def test_mqtt_msg_entropy_matches_text(self):
        try:
            import pandas as pd
        except ImportError:
            raise unittest.SkipTest('pandas no instalado')
        common_mod = common()
        text = '48454c4c4f'
        df = pd.DataFrame({'frame.len': [60.0], 'frame.time_delta': [0.01],
                           'mqtt.msg': [text], 'mqtt.hdrflags': ['0x30']})
        features = common_mod.build_mqtt_features(df)
        self.assertEqual(float(features['fe_msg_entropy'].iloc[0]),
                         common_mod.entropia(text))


class SupervisedLstmAdapterTests(unittest.TestCase):
    def build_model_dir(self, directory):
        try:
            import joblib
            import numpy as np
            import pandas as pd
            import torch
            import torch.nn as nn
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            raise unittest.SkipTest('torch/joblib/scikit-learn no instalados')
        common_mod = common()
        base = list(common_mod.BASE_MODEL_FEATURES)

        class _Tiny(nn.Module):
            def __init__(self, features, hidden=32, classes=4):
                super().__init__()
                self.encoder_lstm = nn.LSTM(features, hidden, batch_first=True)
                self.classifier = nn.Linear(hidden, classes)

            def forward(self, x):
                _, (hidden, _) = self.encoder_lstm(x)
                return self.classifier(hidden[-1])

        torch.manual_seed(0)
        model = _Tiny(len(base))
        torch.jit.script(model).save(os.path.join(directory, 'lstm_classifier.pt'))
        train = pd.DataFrame({column: [0.0, 1.0] for column in base})
        joblib.dump(StandardScaler().fit(train),
                    os.path.join(directory, 'scaler.joblib'))
        with open(os.path.join(directory, 'known_origins.json'), 'w') as handle:
            json.dump({'keys': []}, handle)
        with open(os.path.join(directory, 'known_topics.json'), 'w') as handle:
            json.dump({'keys': []}, handle)
        statistics = {
            'base_columns': base,
            'nan_features': [c for c in common_mod.NAN_FEATURES if c in base],
            'means': {column: 0.0 for column in base},
            'tensor_columns': base + ['missing__' + c for c in base
                                      if c in common_mod.NAN_FEATURES],
        }
        with open(os.path.join(directory, 'nan_statistics.json'), 'w') as handle:
            json.dump(statistics, handle)
        config = {
            'class_names': common_mod.CLASS_NAMES,
            'feature_mode': 'mqtt',
            'observation_mode': 'ethernet_tcp_and_l2',
            'feature_columns_lstm_raw': base,
            'known_origins_artifact': 'known_origins.json',
            'known_topics_artifact': 'known_topics.json',
            'nan_statistics_artifact': 'nan_statistics.json',
        }
        with open(os.path.join(directory, 'pipeline_config.json'), 'w') as handle:
            json.dump(config, handle)
        return base

    def test_predict_returns_four_class_labels(self):
        from infrastructure.classifiers import LstmClassifier
        with tempfile.TemporaryDirectory() as directory:
            base = self.build_model_dir(directory)
            classifier = LstmClassifier(model_dir=directory, device='cpu')
            window = [{column: 1.0 for column in base} for _ in range(11)]
            labels = classifier.predict(window)
            self.assertTrue(labels)
            self.assertTrue(all(label in common().CLASS_NAMES for label in labels))


if __name__ == '__main__':
    unittest.main()
