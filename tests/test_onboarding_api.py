import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
    from detection.http import ApiSettings, build_container, create_app
    from detection.http.onboarding import OnboardingConfig, sensor_status
    from detection.infrastructure.repositories.registry_sqlite import connect
    from detection.infrastructure.sensor_tokens import SensorTokenService
except ImportError as exc:  # fastapi, httpx or pyjwt missing
    raise unittest.SkipTest(f'API test dependencies missing: {exc}')

SECRET = 'test-secret-with-enough-length-0123456789'
CA_PEM = '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n'


def _auth(user_id):
    token = PyJwtTokenService(SECRET, 15, 10080).create_access(user_id)
    return {'Authorization': f'Bearer {token}'}


class OnboardingApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        ca = root / 'ca.crt'
        ca.write_text(CA_PEM, encoding='utf-8')
        self.onboarding = OnboardingConfig(
            public_api_url='https://api.example.com',
            agent_endpoint='tls://agent.example.com:8443',
            agent_ca_path=ca, capture_image='agentiot/capture:1')
        self.container = build_container(
            db_path=str(root / 'detection.db'), jwt_secret=SECRET,
            alerts_dir=root / 'alerts', sensor_ttl_minutes=60,
            onboarding=self.onboarding)
        settings = ApiSettings(root / 'r.json', 'http://ollama', 'm', 5.0, 'UTC')
        self.client = TestClient(create_app(settings, container=self.container))
        self.client.__enter__()
        self.headers = _auth('user-1')

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def _create(self, headers=None):
        response = self.client.post('/api/v1/brokers', json={
            'name': 'bodega', 'host': 'mqtt.cliente.com', 'port': 1883},
            headers=headers or self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _enroll(self, key, name='host-1'):
        return self.client.post('/api/v1/sensors/enroll',
                                json={'enrollment_key': key, 'name': name})

    def _broker(self, broker_id):
        return self.client.get(f'/api/v1/brokers/{broker_id}',
                               headers=self.headers).json()

    def test_create_broker_returns_key_and_install_command(self):
        broker = self._create()
        key = broker['enrollment_key']
        self.assertTrue(key.startswith('ek_'))
        self.assertGreaterEqual(len(key), 40)
        self.assertEqual(broker['status'], 'pending')
        self.assertIn(f'ENROLL_KEY={key}', broker['install_command'])
        self.assertIn('API_URL=https://api.example.com', broker['install_command'])
        self.assertIn('agentiot/capture:1', broker['install_command'])
        listed = self.client.get('/api/v1/brokers', headers=self.headers).json()
        self.assertNotIn('enrollment_key', listed[0])
        row = self.container.connection.execute(
            'SELECT enrollment_key_hash FROM brokers').fetchone()[0]
        self.assertNotEqual(row, key)
        self.assertEqual(len(row), 64)

    def test_enroll_returns_identity_and_agent_settings(self):
        broker = self._create()
        response = self._enroll(broker['enrollment_key'])
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body['tenant_id'], 'user-1')
        self.assertEqual(body['broker_id'], broker['id'])
        self.assertTrue(body['sensor_secret'].startswith('ss_'))
        self.assertEqual(body['agent_endpoint'], 'tls://agent.example.com:8443')
        self.assertEqual(body['agent_server_name'], 'agente')
        self.assertEqual(body['agent_ca'], CA_PEM)
        self.assertEqual(body['expires_in'], 3600)
        claims = SensorTokenService(SECRET).decode(body['access_token'])
        self.assertEqual(claims['sensor_id'], body['sensor_id'])
        status = self._broker(broker['id'])
        self.assertEqual(status['status'], 'connected')
        self.assertEqual(status['sensor_id'], body['sensor_id'])

    def test_enrolled_sensor_can_ingest_alerts(self):
        body = self._enroll(self._create()['enrollment_key']).json()
        response = self.client.post('/api/v1/alerts', json={
            'alert_id': 'a-1', 'ts': 1_800_000_000.0, 'label': 'ataque'},
            headers={'Authorization': f"Bearer {body['access_token']}"})
        self.assertEqual(response.status_code, 201, response.text)
        alerts = self.client.get('/api/v1/alerts', headers=self.headers).json()
        self.assertEqual(alerts[0]['sensor_id'], body['sensor_id'])

    def test_invalid_key_is_rejected(self):
        self._create()
        response = self._enroll('ek_' + 'x' * 43)
        self.assertEqual(response.status_code, 401)

    def test_refresh_issues_token_and_updates_last_seen(self):
        body = self._enroll(self._create()['enrollment_key']).json()
        self.container.connection.execute(
            "UPDATE sensors SET last_seen = '2020-01-01T00:00:00+00:00'")
        self.container.connection.commit()
        response = self.client.post(
            '/api/v1/sensors/token/refresh',
            headers={'Authorization': f"Bearer {body['sensor_secret']}"})
        self.assertEqual(response.status_code, 200, response.text)
        claims = SensorTokenService(SECRET).decode(response.json()['access_token'])
        self.assertEqual(claims['broker_id'], body['broker_id'])
        self.assertEqual(self._broker(body['broker_id'])['status'], 'connected')

    def test_refresh_rejects_unknown_secret(self):
        response = self.client.post('/api/v1/sensors/token/refresh',
                                    headers={'Authorization': 'Bearer ss_nope'})
        self.assertEqual(response.status_code, 401)
        response = self.client.post('/api/v1/sensors/token/refresh')
        self.assertEqual(response.status_code, 401)

    def test_reinstall_keeps_one_sensor_and_revokes_previous(self):
        broker = self._create()
        first = self._enroll(broker['enrollment_key'], 'old').json()
        second = self._enroll(broker['enrollment_key'], 'new').json()
        self.assertEqual(first['sensor_id'], second['sensor_id'])
        sensors = self.client.get(f"/api/v1/brokers/{broker['id']}/sensors",
                                  headers=self.headers).json()
        self.assertEqual([s['name'] for s in sensors], ['new'])
        old = self.client.post('/api/v1/sensors/token/refresh', headers={
            'Authorization': f"Bearer {first['sensor_secret']}"})
        self.assertEqual(old.status_code, 401)
        new = self.client.post('/api/v1/sensors/token/refresh', headers={
            'Authorization': f"Bearer {second['sensor_secret']}"})
        self.assertEqual(new.status_code, 200)

    def test_rotate_key_revokes_old_key_and_sensor(self):
        broker = self._create()
        enrolled = self._enroll(broker['enrollment_key']).json()
        response = self.client.post(
            f"/api/v1/brokers/{broker['id']}/enrollment-key", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        new_key = response.json()['enrollment_key']
        self.assertNotEqual(new_key, broker['enrollment_key'])
        self.assertIn(new_key, response.json()['install_command'])
        self.assertEqual(self._enroll(broker['enrollment_key']).status_code, 401)
        refresh = self.client.post('/api/v1/sensors/token/refresh', headers={
            'Authorization': f"Bearer {enrolled['sensor_secret']}"})
        self.assertEqual(refresh.status_code, 401)
        self.assertEqual(self._broker(broker['id'])['status'], 'offline')
        self.assertEqual(self._enroll(new_key).status_code, 201)

    def test_rotate_and_get_are_scoped_to_owner(self):
        broker = self._create()
        other = _auth('user-2')
        self.assertEqual(self.client.post(
            f"/api/v1/brokers/{broker['id']}/enrollment-key",
            headers=other).status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/brokers/{broker['id']}",
                                         headers=other).status_code, 404)

    def test_deleting_broker_revokes_sensor(self):
        broker = self._create()
        enrolled = self._enroll(broker['enrollment_key']).json()
        self.client.delete(f"/api/v1/brokers/{broker['id']}", headers=self.headers)
        refresh = self.client.post('/api/v1/sensors/token/refresh', headers={
            'Authorization': f"Bearer {enrolled['sensor_secret']}"})
        self.assertEqual(refresh.status_code, 401)
        self.assertEqual(self._enroll(broker['enrollment_key']).status_code, 401)

    def test_second_manual_sensor_conflicts(self):
        broker = self._create()
        url = f"/api/v1/brokers/{broker['id']}/sensors"
        self.assertEqual(self.client.post(url, json={'name': 's1'},
                                          headers=self.headers).status_code, 201)
        self.assertEqual(self.client.post(url, json={'name': 's2'},
                                          headers=self.headers).status_code, 409)


class SensorStatusTests(unittest.TestCase):
    def test_status_values(self):
        now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        recent = (now - timedelta(seconds=30)).isoformat()
        old = (now - timedelta(minutes=10)).isoformat()
        self.assertEqual(sensor_status(None, 180, now), 'pending')
        self.assertEqual(sensor_status(
            {'last_seen': recent, 'secret_hash': 'h'}, 180, now), 'connected')
        self.assertEqual(sensor_status(
            {'last_seen': old, 'secret_hash': 'h'}, 180, now), 'offline')
        self.assertEqual(sensor_status(
            {'last_seen': recent, 'secret_hash': None}, 180, now), 'offline')


class MigrationTests(unittest.TestCase):
    def test_old_database_gets_new_columns_and_keeps_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'old.db')
            old = sqlite3.connect(path)
            old.executescript("""
                CREATE TABLE brokers (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL, host TEXT, port INTEGER,
                    created_at TEXT NOT NULL);
                CREATE TABLE sensors (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                    broker_id TEXT NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, created_at TEXT NOT NULL);
                INSERT INTO brokers VALUES ('b1', 't1', 'viejo', NULL, NULL, 'x');
                INSERT INTO sensors VALUES ('s1', 't1', 'b1', 'cap', 'x');
            """)
            old.close()
            for _ in range(2):  # idempotent
                conn = connect(path)
                broker_columns = {r[1] for r in conn.execute(
                    'PRAGMA table_info(brokers)')}
                sensor_columns = {r[1] for r in conn.execute(
                    'PRAGMA table_info(sensors)')}
                self.assertIn('enrollment_key_hash', broker_columns)
                self.assertTrue({'secret_hash', 'last_seen'} <= sensor_columns)
                self.assertEqual(conn.execute(
                    'SELECT name FROM brokers').fetchall()[0][0], 'viejo')
                conn.close()


if __name__ == '__main__':
    unittest.main()
