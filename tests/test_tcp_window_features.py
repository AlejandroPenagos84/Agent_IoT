from pathlib import Path
import importlib.util
import math
import sys
import unittest

from infrastructure.tshark.tcp_window_features import (
    TCP_FEATURE_COLUMNS, TcpWindowFeatures,
)

ROOT = Path(__file__).resolve().parents[1]
HAS_PANDAS = all(importlib.util.find_spec(m) for m in ('numpy', 'pandas'))


def frame(t, src, sport, dst, dport, length=100, delta=0.01, msgtype=None):
    return {'frame.time_epoch': t, 'ip.src': src, 'tcp.srcport': sport,
            'ip.dst': dst, 'tcp.dstport': dport, 'frame.len': length,
            'frame.time_delta': delta, 'mqtt.msgtype': msgtype}


class TcpWindowFeatureTests(unittest.TestCase):
    def test_out_of_scope_and_incomplete_frames_return_none(self):
        builder = TcpWindowFeatures()
        self.assertIsNone(builder.update(frame(1.0, '10.0.0.1', 40000, '10.0.0.2', 443)))
        self.assertIsNone(builder.update(frame(1.0, None, 40000, '10.0.0.2', 1883)))
        self.assertIsNone(builder.update({'tcp.srcport': 40000, 'tcp.dstport': 1883}))

    def test_first_frame_has_no_history_and_columns_follow_model_order(self):
        features = TcpWindowFeatures().update(
            frame(1.0, '10.0.0.1', 40000, '10.0.0.2', 1883, length=60, msgtype='1'))
        self.assertEqual(list(features), list(TCP_FEATURE_COLUMNS))
        self.assertEqual(features['frame.len'], 60)
        self.assertAlmostEqual(features['fe_log_len'], math.log1p(60))
        self.assertEqual(features['fe_is_standard_mqtt_port'], 1.0)
        self.assertEqual(features['fe_is_broker_to_client'], 0.0)
        for name in TCP_FEATURE_COLUMNS[5:]:
            self.assertEqual(features[name], 0.0, name)

    def test_windows_are_causal_and_expire_after_five_seconds(self):
        builder = TcpWindowFeatures()
        builder.update(frame(0.0, '10.0.0.1', 40000, '10.0.0.2', 1883, length=100))
        second = builder.update(frame(1.0, '10.0.0.1', 40000, '10.0.0.2', 1883, length=300))
        self.assertEqual(second['tcp_frames_5s'], 1.0)            # solo el anterior
        self.assertAlmostEqual(second['tcp_bytes_5s'], math.log1p(100))
        self.assertEqual(second['tcp_iat'], 1.0)
        self.assertEqual(second['tcp_new_conns_5s'], 1.0)         # el par del frame 0
        reply = builder.update(frame(1.5, '10.0.0.2', 1883, '10.0.0.1', 40000))
        self.assertEqual(reply['fe_is_broker_to_client'], 1.0)
        self.assertEqual(reply['tcp_frames_5s'], 0.0)             # otra dirección
        self.assertEqual(reply['tcp_asymmetry_5s'], 1.0)          # 2/2 hacia el broker
        late = builder.update(frame(6.5, '10.0.0.1', 40000, '10.0.0.2', 1883))
        self.assertEqual(late['tcp_frames_5s'], 0.0)              # t=1 y t=0 expiraron
        self.assertEqual(late['tcp_new_conns_5s'], 0.0)

    def test_connect_starts_a_new_session_for_the_same_endpoints(self):
        builder = TcpWindowFeatures()
        builder.update(frame(0.0, '10.0.0.1', 40000, '10.0.0.2', 1883, msgtype='1'))
        reconnect = builder.update(frame(0.5, '10.0.0.1', 40000, '10.0.0.2', 1883, msgtype='1'))
        self.assertEqual(reconnect['tcp_frames_5s'], 0.0)
        self.assertEqual(reconnect['tcp_iat'], 0.0)

    @unittest.skipUnless(HAS_PANDAS and (ROOT / 'dataset' / 'DoS.csv').is_file(),
                         'requiere numpy/pandas y dataset/DoS.csv')
    def test_matches_offline_training_features_on_dos_capture(self):
        sys.path.insert(0, str(ROOT / 'ML_Model'))
        try:
            from data_preprocessing.load_data import load_capture
            from data_preprocessing.tcp_features import (
                TCP_FEATURE_COLUMNS as OFFLINE_COLUMNS, build_tcp_features,
            )
        finally:
            sys.path.remove(str(ROOT / 'ML_Model'))
        import numpy as np
        import pandas as pd

        self.assertEqual(list(TCP_FEATURE_COLUMNS), OFFLINE_COLUMNS)
        data = load_capture('DoS', ROOT / 'dataset' / 'DoS.csv')
        ports = data[['tcp.srcport', 'tcp.dstport']]
        scope = data.loc[ports.isin([1883, 8883]).any(axis=1)]
        offline = build_tcp_features(scope)

        builder = TcpWindowFeatures()
        columns = ['ip.src', 'tcp.srcport', 'ip.dst', 'tcp.dstport', 'frame.time_epoch',
                   'frame.len', 'frame.time_delta', 'mqtt.msgtype']
        online = pd.DataFrame(
            [builder.update(dict(zip(columns, values)))
             for values in scope[columns].itertuples(index=False, name=None)],
            index=scope.index)[OFFLINE_COLUMNS]
        np.testing.assert_allclose(online.to_numpy(), offline.to_numpy(), rtol=0, atol=1e-9)


if __name__ == '__main__':
    unittest.main()
