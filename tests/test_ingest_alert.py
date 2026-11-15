"""IngestAlert: una alerta entra una sola vez a la base y al diario JSONL."""

import json
import tempfile
import unittest
from pathlib import Path

from detection.application.use_cases.ingest_alert import IngestAlert
from detection.domain.model import Alert
from detection.infrastructure.repositories.alert_repository_sqlite import SqliteAlertRepository
from detection.infrastructure.repositories.registry_sqlite import RegistryStore, connect
from detection.infrastructure.sinks import CompositeAlertSink, DailyFileAlertSink, IngestAlertSink


def _alert(alert_id, tenant='t1'):
    return Alert(
        ts=1_800_000_000.0,
        kind='class',
        label='ataque',
        alert_id=alert_id,
        tenant_id=tenant,
        broker_id='b1',
        sensor_id='s1',
    )


class IngestAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.journal_dir = Path(self.tmp.name) / 'alerts'
        self.connection = connect(':memory:')
        self.addCleanup(self.connection.close)
        self.store = RegistryStore(self.connection)
        self.ingest = IngestAlert(
            SqliteAlertRepository(self.store), DailyFileAlertSink(self.journal_dir)
        )

    def journal(self):
        return [
            json.loads(line)['alert_id']
            for path in sorted(self.journal_dir.glob('*.jsonl'))
            for line in path.read_text().splitlines()
        ]

    def test_new_alert_goes_to_store_and_journal(self):
        self.assertTrue(self.ingest.execute(_alert('a1')))
        self.assertEqual(self.store.get_alert('t1', 'a1')['broker_id'], 'b1')
        self.assertEqual(self.journal(), ['a1'])

    def test_duplicate_is_not_written_twice(self):
        self.ingest.execute(_alert('a1'))
        self.assertFalse(self.ingest.execute(_alert('a1')))
        self.assertEqual(self.journal(), ['a1'])

    def test_alert_without_tenant_only_goes_to_journal(self):
        self.assertFalse(self.ingest.execute(_alert('local', tenant=None)))
        self.assertEqual(self.store.list_alerts('t1'), [])
        self.assertEqual(self.journal(), ['local'])

    def test_agent_sink_delivers_through_the_use_case(self):
        sink = CompositeAlertSink([IngestAlertSink(self.ingest)])
        sink.emit(_alert('from-agent'))
        self.assertIsNotNone(self.store.get_alert('t1', 'from-agent'))
        self.assertEqual(self.journal(), ['from-agent'])


class BuildAgentWiringTests(unittest.TestCase):
    """build_agent usa IngestAlert y solo añade MQTT si hay broker."""

    MODEL_DIR = Path(__file__).resolve().parents[1] / 'modelos_agente_tcp'

    def setUp(self):
        try:
            from detection.composition_root import AgentConfig, build_agent
        except ImportError as exc:
            self.skipTest(f'agent dependencies missing: {exc}')
        self.AgentConfig, self.build_agent = AgentConfig, build_agent
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        connection = connect(':memory:')
        self.addCleanup(connection.close)
        self.ingest = IngestAlert(
            SqliteAlertRepository(RegistryStore(connection)), DailyFileAlertSink(root / 'alerts')
        )
        self.cfg = AgentConfig(
            capture_endpoint=f'unix://{root}/f.sock',
            model_dir=str(self.MODEL_DIR),
            evidence_dir=str(root / 'evidence'),
        )

    def test_sinks_without_mqtt(self):
        server = self.build_agent(self.cfg, self.ingest)
        sink = server.closeables[0]
        self.assertEqual([type(s).__name__ for s in sink.sinks], ['IngestAlertSink'])

    def test_tls_endpoint_requires_sensor_tokens(self):
        cfg = self.AgentConfig(
            capture_endpoint='tls://127.0.0.1:0',
            model_dir=str(self.MODEL_DIR),
            evidence_dir=self.cfg.evidence_dir,
            tls_cert='x',
            tls_key='y',
        )
        with self.assertRaises(ValueError):
            self.build_agent(cfg, self.ingest, sensor_tokens=None)


if __name__ == '__main__':
    unittest.main()
