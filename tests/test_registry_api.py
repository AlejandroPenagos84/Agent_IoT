import json
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
    from detection.http import ApiSettings, build_container, create_app
    from detection.infrastructure.sensor_tokens import AgentTokenService
except ImportError as exc:  # fastapi, httpx, pydantic or pyjwt missing
    raise unittest.SkipTest(f"API test dependencies missing: {exc}")

SECRET = 'test-secret'


class RegistryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.alerts_dir = root / 'alerts'
        self.container = build_container(
            db_path=str(root / 'detection.db'), jwt_secret=SECRET,
            alerts_dir=self.alerts_dir, sensor_ttl_minutes=60)
        settings = ApiSettings(
            report_path=root / 'report.json',
            ollama_url='http://ollama:11434',
            ollama_model='gemma3:4b',
            ollama_timeout=5.0,
        )
        self.client = TestClient(create_app(settings, container=self.container))
        self.client.__enter__()
        self.tokens = PyJwtTokenService(SECRET, 15, 10080)
        self.headers = self._auth('user-1')

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    @staticmethod
    def _auth(user_id):
        token = PyJwtTokenService(SECRET, 15, 10080).create_access(user_id)
        return {'Authorization': f'Bearer {token}'}

    def _create_broker(self, headers=None):
        response = self.client.post('/api/v1/brokers',
                                    json={'name': 'broker-1', 'host': 'mqtt',
                                          'port': 1883},
                                    headers=headers or self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_requires_authentication(self):
        response = self.client.get('/api/v1/brokers')
        self.assertEqual(response.status_code, 401)

    def test_broker_and_sensor_registry(self):
        broker = self._create_broker()
        self.assertEqual(broker['tenant_id'], 'user-1')

        response = self.client.get('/api/v1/brokers', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()], [broker['id']])

        response = self.client.post(
            f"/api/v1/brokers/{broker['id']}/sensors",
            json={'name': 'sensor-1'}, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        sensor = response.json()
        self.assertEqual(sensor['broker_id'], broker['id'])

        response = self.client.get(
            f"/api/v1/brokers/{broker['id']}/sensors", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.json()], [sensor['id']])

    def test_sensor_token_and_alert_ingestion(self):
        broker = self._create_broker()
        sensor = self.client.post(
            f"/api/v1/brokers/{broker['id']}/sensors",
            json={'name': 'sensor-1'}, headers=self.headers).json()
        response = self.client.post(
            f"/api/v1/sensors/{sensor['id']}/token", headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        sensor_token = response.json()['access_token']
        sensor_headers = {'Authorization': f'Bearer {sensor_token}'}

        alert = {
            'alert_id': 'alert-1', 'ts': 1_800_000_000.0, 'kind': 'class',
            'label': 'ataque', 'client_id': 'sensor1', 'ip': '10.0.0.1',
            'topic': 'home/temp', 'source': 'tshark-tcp',
        }
        response = self.client.post('/api/v1/alerts', json=alert,
                                    headers=sensor_headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()['stored'])

        response = self.client.post('/api/v1/alerts', json=alert,
                                    headers=sensor_headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertFalse(response.json()['stored'])

        response = self.client.get('/api/v1/alerts', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        alerts = response.json()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['tenant_id'], 'user-1')
        self.assertEqual(alerts[0]['broker_id'], broker['id'])
        self.assertEqual(alerts[0]['sensor_id'], sensor['id'])

        daily = list(self.alerts_dir.glob('*.jsonl'))
        self.assertEqual(len(daily), 1)
        self.assertEqual(json.loads(daily[0].read_text())['alert_id'], 'alert-1')

    def test_delete_broker_cascades_sensors_and_keeps_alerts(self):
        broker = self._create_broker()
        sensor = self.client.post(
            f"/api/v1/brokers/{broker['id']}/sensors",
            json={'name': 'sensor-1'}, headers=self.headers).json()
        token = self.client.post(
            f"/api/v1/sensors/{sensor['id']}/token",
            headers=self.headers).json()['access_token']
        self.client.post('/api/v1/alerts', json={
            'alert_id': 'alert-1', 'ts': 1_800_000_000.0, 'label': 'ataque',
        }, headers={'Authorization': f'Bearer {token}'})

        response = self.client.delete(
            f"/api/v1/brokers/{broker['id']}", headers=self.headers)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.client.get('/api/v1/brokers',
                                         headers=self.headers).json(), [])
        response = self.client.get(
            f"/api/v1/brokers/{broker['id']}/sensors", headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.client.get('/api/v1/alerts',
                                             headers=self.headers).json()), 1)
        response = self.client.delete(
            f"/api/v1/brokers/{broker['id']}", headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_delete_broker_is_scoped_to_owner(self):
        broker = self._create_broker()
        response = self.client.delete(
            f"/api/v1/brokers/{broker['id']}", headers=self._auth('user-2'))
        self.assertEqual(response.status_code, 404)
        brokers = self.client.get('/api/v1/brokers', headers=self.headers).json()
        self.assertEqual([item['id'] for item in brokers], [broker['id']])

    def test_tenant_isolation(self):
        broker = self._create_broker()
        other = self._auth('user-2')
        response = self.client.get('/api/v1/brokers', headers=other)
        self.assertEqual(response.json(), [])
        response = self.client.post('/api/v1/brokers', json={'name': 'x'},
                                    headers=other)
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.json()['id'], broker['id'])


    def test_agent_token_ingests_alert_with_identity(self):
        token, _ = AgentTokenService(SECRET).create('user-1')
        headers = {'Authorization': f'Bearer {token}'}
        response = self.client.post('/api/v1/alerts', json={
            'alert_id': 'agent-alert-1', 'ts': 1_800_000_000.0,
            'label': 'ataque', 'tenant_id': 'user-1', 'broker_id': 'b1',
            'sensor_id': 's1',
        }, headers=headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()['stored'])
        alerts = self.client.get('/api/v1/alerts',
                                 headers=self.headers).json()
        self.assertEqual(alerts[0]['broker_id'], 'b1')
        self.assertEqual(alerts[0]['sensor_id'], 's1')

    def test_list_alerts_filters_by_time_window(self):
        token, _ = AgentTokenService(SECRET).create('user-1')
        headers = {'Authorization': f'Bearer {token}'}
        for index, ts in enumerate((100.0, 200.0, 300.0)):
            response = self.client.post('/api/v1/alerts', json={
                'alert_id': f'w-{index}', 'ts': ts, 'label': 'ataque',
                'tenant_id': 'user-1'}, headers=headers)
            self.assertEqual(response.status_code, 201, response.text)

        def ids(**params):
            response = self.client.get('/api/v1/alerts', params=params,
                                       headers=self.headers)
            self.assertEqual(response.status_code, 200, response.text)
            return [item['alert_id'] for item in response.json()]

        self.assertEqual(ids(since='200'), ['w-2', 'w-1'])
        self.assertEqual(ids(until='200'), ['w-0'])
        self.assertEqual(ids(since='150', until='250'), ['w-1'])
        self.assertEqual(ids(since='1970-01-01T00:03:20Z',
                             until='1970-01-01T00:05:00+00:00'), ['w-1'])

        for params in ({'since': 'ayer'}, {'since': '1970-01-01T00:00:00'},
                       {'since': '300', 'until': '100'}):
            response = self.client.get('/api/v1/alerts', params=params,
                                       headers=self.headers)
            self.assertEqual(response.status_code, 400, params)

    def test_agent_token_cannot_cross_tenants(self):
        token, _ = AgentTokenService(SECRET).create('user-1')
        response = self.client.post('/api/v1/alerts', json={
            'alert_id': 'agent-alert-2', 'ts': 1.0, 'label': 'ataque',
            'tenant_id': 'user-2',
        }, headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(response.status_code, 403)

    def test_sensor_token_cannot_claim_other_sensor(self):
        broker = self._create_broker()
        sensor = self.client.post(
            f"/api/v1/brokers/{broker['id']}/sensors",
            json={'name': 'sensor-1'}, headers=self.headers).json()
        token = self.client.post(
            f"/api/v1/sensors/{sensor['id']}/token",
            headers=self.headers).json()['access_token']
        response = self.client.post('/api/v1/alerts', json={
            'alert_id': 'alert-1', 'ts': 1.0, 'label': 'ataque',
            'sensor_id': 'other-sensor',
        }, headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
