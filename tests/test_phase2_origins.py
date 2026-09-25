"""Fase 2: `fe_origen_conocido` y `fe_origen_observable`.

El par distingue identidad ausente `(0, 0)` de origen observado pero desconocido
`(0, 1)`. El lookup usa claves prefijadas `ip:`/`client:` de una allowlist
aprendida solo de train, sobre la identidad presente en el frame.
"""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from infrastructure.classifiers._common import (
    MODEL_FEATURES, add_stage2_features, build_mqtt_features, load_known_origins,
)
from infrastructure.tshark.stream_features import FIELDS, record_from_fields
from infrastructure.tshark.tshark_feature_source import TsharkFeatureSource


def origins(ip=None, client=None, known=frozenset(), origin_column='ip.src'):
    raw = pd.DataFrame([{origin_column: ip, 'mqtt.clientid': client}])
    features = add_stage2_features(build_mqtt_features(raw), raw, known,
                                   frozenset())
    row = features.iloc[0]
    return int(row['fe_origen_conocido']), int(row['fe_origen_observable'])


class OriginFeatureTests(unittest.TestCase):
    KNOWN = frozenset({'ip:10.0.0.1', 'client:sensor1'})

    def test_known_ip(self):
        self.assertEqual(origins('10.0.0.1', None, self.KNOWN), (1, 1))

    def test_known_client(self):
        self.assertEqual(origins(None, 'sensor1', self.KNOWN), (1, 1))

    def test_both_unknown(self):
        self.assertEqual(origins('9.9.9.9', 'rogue', self.KNOWN), (0, 1))

    def test_both_absent(self):
        self.assertEqual(origins(None, None, self.KNOWN), (0, 0))

    def test_known_ip_with_unknown_client_is_known(self):
        self.assertEqual(origins('10.0.0.1', 'rogue', self.KNOWN), (1, 1))

    def test_known_client_with_unknown_ip_is_known(self):
        self.assertEqual(origins('9.9.9.9', 'sensor1', self.KNOWN), (1, 1))

    def test_spaces_are_trimmed(self):
        self.assertEqual(origins('  10.0.0.1  ', ' sensor1 ', self.KNOWN), (1, 1))

    def test_empty_strings_are_absent(self):
        self.assertEqual(origins('', '', self.KNOWN), (0, 0))

    def test_prefixes_are_not_interchangeable(self):
        # El texto de una clave no coincide con el prefijo de la otra.
        self.assertEqual(origins('client:sensor1', None, self.KNOWN), (0, 1))
        self.assertEqual(origins(None, '10.0.0.1', self.KNOWN), (0, 1))

    def test_client_case_is_preserved(self):
        known = frozenset({'client:Sensor1'})
        self.assertEqual(origins(None, 'Sensor1', known), (1, 1))
        self.assertEqual(origins(None, 'sensor1', known), (0, 1))

    def test_mac_is_not_identity(self):
        raw = pd.DataFrame([{'eth.src': 'aa:bb:cc:dd:ee:ff',
                             'eth.dst': 'ff:ff:ff:ff:ff:ff'}])
        features = add_stage2_features(build_mqtt_features(raw), raw,
                                       frozenset(), frozenset())
        row = features.iloc[0]
        self.assertEqual(int(row['fe_origen_conocido']), 0)
        self.assertEqual(int(row['fe_origen_observable']), 0)

    def test_identity_from_other_partition_is_unknown(self):
        # La allowlist viene solo de train; otra partición no la amplía.
        self.assertEqual(origins('172.16.0.9', None, self.KNOWN), (0, 1))

    def test_offline_and_online_columns_agree(self):
        offline = origins('10.0.0.1', 'rogue', self.KNOWN, origin_column='ip.src')
        online = origins('10.0.0.1', 'rogue', self.KNOWN,
                         origin_column='_origin_ip')
        self.assertEqual(offline, online)
        self.assertEqual(
            origins(None, None, self.KNOWN, origin_column='_origin_ip'), (0, 0))

    def test_origin_features_are_a_removable_block(self):
        # La ablación de Fase 5 quita las dos features de origen como un bloque.
        block = ['fe_origen_conocido', 'fe_origen_observable']
        start = MODEL_FEATURES.index(block[0])
        self.assertEqual(MODEL_FEATURES[start:start + 2], block)
        without = [name for name in MODEL_FEATURES if name not in block]
        self.assertEqual(len(without), len(MODEL_FEATURES) - 2)
        self.assertFalse(set(block) & set(without))

    def test_full_feature_parity_offline_online(self):
        offline_raw = pd.DataFrame([{
            'ip.src': '10.0.0.1', 'mqtt.clientid': 'rogue',
            'frame.len': 60.0, 'frame.time_delta': 0.01}])
        online_raw = offline_raw.rename(columns={'ip.src': '_origin_ip'})
        offline = add_stage2_features(
            build_mqtt_features(offline_raw), offline_raw, self.KNOWN, frozenset())
        online = add_stage2_features(
            build_mqtt_features(online_raw), online_raw, self.KNOWN, frozenset())
        pd.testing.assert_frame_equal(offline, online)


class OriginArtifactTests(unittest.TestCase):
    def test_missing_artifact_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = {'known_origins_artifact': 'known_origins.json'}
            with self.assertRaises(ValueError):
                load_known_origins(directory, cfg)

    def test_undeclared_artifact_raises(self):
        with self.assertRaises(ValueError):
            load_known_origins('/tmp', {})

    def test_artifact_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            load_known_origins('/tmp', {
                'known_origins_artifact': '../known_origins.json'})

    def test_keys_are_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'known_origins.json'
            path.write_text(json.dumps(
                {'keys': ['ip:1.2.3.4', 'client:a']}), encoding='utf-8')
            keys = load_known_origins(directory, {
                'known_origins_artifact': 'known_origins.json'})
            self.assertEqual(keys, frozenset({'ip:1.2.3.4', 'client:a'}))


class CorrelatedMetadataTests(unittest.TestCase):
    def test_correlated_client_id_does_not_enter_frame_lookup(self):
        source = TsharkFeatureSource()
        connect = record_from_fields([
            {'tcp.stream': '7', 'mqtt.msgtype': '1',
             'mqtt.clientid': 'sensor1'}.get(field, '') for field in FIELDS])
        source._context(connect)
        publish = record_from_fields([
            {'tcp.stream': '7', 'mqtt.msgtype': '3'}.get(field, '')
            for field in FIELDS])
        context = source._context(publish)
        features = source._features(publish)
        # El client_id se correlaciona para la alerta, pero el frame no lo trae.
        self.assertEqual(context.client_id, 'sensor1')
        self.assertIsNone(features.get('mqtt.clientid'))
        raw = pd.DataFrame([features])
        stage2 = add_stage2_features(build_mqtt_features(raw), raw,
                                     frozenset({'client:sensor1'}), frozenset())
        row = stage2.iloc[0]
        self.assertEqual(int(row['fe_origen_conocido']), 0)
        self.assertEqual(int(row['fe_origen_observable']), 0)


if __name__ == '__main__':
    unittest.main()
