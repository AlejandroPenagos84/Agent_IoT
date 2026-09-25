"""Fase 3: contexto causal, hdrflags y contrato de preprocesado (faltantes).

Cubre límites de ventana (5 s, 100 µs), retrocesos de reloj, reinicio de
CONNECT, tensor de imputación con máscaras y decodificación validada de
`mqtt.hdrflags`. No entrena ni ejecuta el notebook.
"""
import json
import math
import os
import tempfile
import unittest

from application.ports.ports_out import FeatureSource
from application.ports.types import Frame
from domain.model import FrameContext
from infrastructure.features import ContextFeatureSource
from infrastructure.tshark.stream_features import FIELDS, record_from_fields
from infrastructure.tshark.tshark_feature_source import TsharkFeatureSource


def tools():
    try:
        import numpy as np
        import pandas as pd
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        raise unittest.SkipTest('numpy/pandas/scikit-learn no instalados')
    return np, pd, StandardScaler


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


def origin_frame(ip, epoch, length=60.0, msgtype=3):
    return Frame({'frame.time_epoch': epoch, 'frame.len': length,
                  'mqtt.msgtype': msgtype},
                 FrameContext(ts=epoch, ip=ip))


def eth_frame(eth_src, eth_dst, epoch, ip=None):
    return Frame({'frame.time_epoch': epoch, 'frame.len': 60.0,
                  'mqtt.msgtype': None},
                 FrameContext(ts=epoch, eth_src=eth_src, eth_dst=eth_dst, ip=ip))


class WindowLimitTests(unittest.TestCase):
    def collect(self, frames, window=5.0):
        builder = ContextFeatureSource(StubSource(frames), window_seconds=window)
        builder.start()
        return list(builder.rows())

    def test_exactly_five_seconds_counts(self):
        rows = self.collect([origin_frame('a', 0.0), origin_frame('a', 5.0)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 1 / 5)

    def test_above_five_seconds_evicts(self):
        rows = self.collect([origin_frame('a', 0.0), origin_frame('a', 5.0001)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 0.0)

    def test_equal_timestamps_count_for_later_frames(self):
        rows = self.collect([origin_frame('a', 2.0), origin_frame('a', 2.0)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 1 / 5)

    def test_clock_rollback_clears_origin_history(self):
        rows = self.collect([origin_frame('a', 10.0), origin_frame('a', 5.0)])
        self.assertEqual(rows[1].features['_ctx_origen_frames_s'], 0.0)

    def test_absent_ip_keeps_nan(self):
        rows = self.collect([origin_frame(None, 0.0)])
        self.assertTrue(math.isnan(rows[0].features['_ctx_origen_frames_s']))

    def test_l2_rates_count_all_frames_by_eth_src(self):
        # Un frame con IP y otro L2 comparten eth.src: ambos cuentan en L2.
        rows = self.collect([
            eth_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 0.0, ip='10.0.0.1'),
            eth_frame('aa:aa:aa:aa:aa:aa', 'cc:cc:cc:cc:cc:cc', 1.0),
        ])
        self.assertEqual(rows[1].features['_ctx_l2_frames_s'], 1 / 5)

    def test_burst_ratio_below_100us(self):
        rows = self.collect([
            eth_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 0.0),
            eth_frame('aa:aa:aa:aa:aa:aa', 'bb:bb:bb:bb:bb:bb', 50e-6),
        ])
        self.assertEqual(rows[1].features['_ctx_l2_burst_ratio'], 1.0)


class HeaderDecodeTests(unittest.TestCase):
    def test_hex_and_decimal_agree(self):
        common_mod = common()
        self.assertEqual(common_mod.decode_hdrflags('0x000000c0')[0], 12)
        self.assertEqual(common_mod.decode_hdrflags('192')[0], 12)

    def test_out_of_byte_is_invalid(self):
        common_mod = common()
        self.assertTrue(all(math.isnan(part)
                            for part in common_mod.decode_hdrflags('0x0100')))

    def test_first_comma_occurrence_is_used(self):
        common_mod = common()
        self.assertEqual(common_mod.decode_hdrflags('0xc0,0x30')[0], 12)
        self.assertEqual(common_mod.decode_hdrflags('1,2')[0], 0)

    def test_missing_is_nan(self):
        common_mod = common()
        for value in (None, '', float('nan')):
            self.assertTrue(all(math.isnan(part)
                                for part in common_mod.decode_hdrflags(value)))

    def test_diagnostics_counts(self):
        common_mod = common()
        result = common_mod.hdrflags_diagnostics(
            [None, '', '0x30', '0x30,0x40', '0x1000'])
        self.assertEqual(result, {'total': 5, 'present': 3, 'multi': 1,
                                  'invalid': 1})


class TensorContractTests(unittest.TestCase):
    def statistics(self):
        return {
            'base_columns': ['a', 'b', 'c'],
            'nan_features': ['a', 'b'],
            'means': {'a': 1.0, 'b': 2.0, 'c': 10.0},
            'tensor_columns': ['a', 'b', 'c', 'missing__a', 'missing__b'],
        }

    def scaler(self, StandardScaler, pd, np):
        train = pd.DataFrame({'a': [0.0, 2.0], 'b': [0.0, 4.0],
                              'c': [3.0, 4.0]})
        return StandardScaler().fit(train)

    def test_impute_scale_zero_and_masks(self):
        np, pd, StandardScaler = tools()
        common_mod = common()
        raw = pd.DataFrame({'a': [1.0, np.nan], 'b': [np.nan, 2.0],
                            'c': [3.0, 4.0]})
        tensor = common_mod.build_tensor(raw, self.scaler(StandardScaler, pd, np),
                                         self.statistics())
        self.assertEqual(tensor.shape, (2, 5))
        # posiciones originalmente ausentes quedan en 0 tras escalar
        self.assertEqual(float(tensor[0, 1]), 0.0)
        self.assertEqual(float(tensor[1, 0]), 0.0)
        # mascaras sin escalar: b ausente en fila 0, a ausente en fila 1
        self.assertEqual(float(tensor[0, 3]), 0.0)
        self.assertEqual(float(tensor[0, 4]), 1.0)
        self.assertEqual(float(tensor[1, 3]), 1.0)
        self.assertEqual(float(tensor[1, 4]), 0.0)
        self.assertTrue(np.isfinite(tensor).all())

    def test_infinite_values_are_rejected(self):
        np, pd, StandardScaler = tools()
        common_mod = common()
        raw = pd.DataFrame({'a': [np.inf], 'b': [1.0], 'c': [1.0]})
        with self.assertRaises(ValueError):
            common_mod.build_tensor(raw, self.scaler(StandardScaler, pd, np),
                                    self.statistics())

    def test_tensor_columns_length_is_checked(self):
        np, pd, StandardScaler = tools()
        common_mod = common()
        statistics = self.statistics()
        statistics['tensor_columns'] = ['a', 'b']
        raw = pd.DataFrame({'a': [1.0], 'b': [2.0], 'c': [3.0]})
        with self.assertRaises(ValueError):
            common_mod.build_tensor(raw, self.scaler(StandardScaler, pd, np),
                                    statistics)

    def test_context_features_are_masked(self):
        common_mod = common()
        for name in ('fe_origen_frames_s', 'fe_origen_bytes_s',
                     'fe_origen_conexiones', 'fe_origen_connects',
                     'fe_l2_frames_s', 'fe_l2_broadcasts', 'fe_l2_burst_ratio',
                     'fe_is_broadcast', 'fe_is_multicast'):
            self.assertIn(name, common_mod.NAN_FEATURES)

    def test_missing_column_is_reported(self):
        np, pd, StandardScaler = tools()
        common_mod = common()
        raw = pd.DataFrame({'a': [1.0]})
        with self.assertRaises(ValueError):
            common_mod.build_tensor(raw, self.scaler(StandardScaler, pd, np),
                                    self.statistics())


class NanStatisticsArtifactTests(unittest.TestCase):
    def test_missing_artifact_raises(self):
        common_mod = common()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                common_mod.load_nan_statistics(directory, {
                    'nan_statistics_artifact': 'nan_statistics.json'})

    def test_invalid_payload_raises(self):
        common_mod = common()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'nan_statistics.json')
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump({'base_columns': 'a'}, handle)
            with self.assertRaises(ValueError):
                common_mod.load_nan_statistics(directory, {
                    'nan_statistics_artifact': 'nan_statistics.json'})

    def test_valid_payload_is_loaded(self):
        common_mod = common()
        payload = {'base_columns': ['a'], 'nan_features': ['a'],
                   'means': {'a': 0.0}, 'tensor_columns': ['a', 'missing__a']}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'nan_statistics.json')
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle)
            loaded = common_mod.load_nan_statistics(directory, {
                'nan_statistics_artifact': 'nan_statistics.json'})
            self.assertEqual(loaded, payload)


class ConnectResetTests(unittest.TestCase):
    def test_new_connect_does_not_inherit_absent_fields(self):
        source = TsharkFeatureSource()
        source._features(record_from_fields([
            {'tcp.stream': '7', 'mqtt.msgtype': '1', 'mqtt.ver': '4.0',
             'mqtt.kalive': '60.0'}.get(field, '') for field in FIELDS]))
        first = source._features(record_from_fields([
            {'tcp.stream': '7', 'mqtt.msgtype': '3'}.get(field, '')
            for field in FIELDS]))
        self.assertEqual(first['_connect_ver'], '4.0')
        self.assertEqual(first['_connect_kalive'], '60.0')
        # Nuevo CONNECT: solo trae ver; kalive no debe heredarse.
        source._features(record_from_fields([
            {'tcp.stream': '7', 'mqtt.msgtype': '1', 'mqtt.ver': '5.0'}
            .get(field, '') for field in FIELDS]))
        second = source._features(record_from_fields([
            {'tcp.stream': '7', 'mqtt.msgtype': '3'}.get(field, '')
            for field in FIELDS]))
        self.assertEqual(second['_connect_ver'], '5.0')
        self.assertIsNone(second['_connect_kalive'])


class TruncationResetTests(unittest.TestCase):
    def test_truncation_clears_connect_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'features.jsonl')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write(json.dumps({
                    'eth.src': 'aa:bb:cc:dd:ee:ff',
                    'eth.dst': 'bb:bb:bb:bb:bb:bb',
                    'frame.time_epoch': 1.0, 'tcp.stream': 7,
                    'mqtt.msgtype': 3}) + '\n')
            source = TsharkFeatureSource(path=path, from_start=True)
            source.start()
            source._connect_state[7] = {'_connect_ver': '4.0'}
            source._offset = 10_000
            next(source.rows())
            source.stop()
            self.assertEqual(source._connect_state, {})


if __name__ == '__main__':
    unittest.main()
