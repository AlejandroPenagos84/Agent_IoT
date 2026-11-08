import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    import uvicorn

    from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
    from detection.http import ApiSettings, build_container, create_app
    from detection.http.onboarding import OnboardingConfig
    from detection.infrastructure.sensor_tokens import (RenewingAgentToken,
                                                        decode_alert_token)
except ImportError as exc:  # API dependencies missing
    raise unittest.SkipTest(f'API test dependencies missing: {exc}')

from detection.infrastructure.tshark.enrollment import (ApiClient,
                                                         EnrollmentError,
                                                         SensorCredentials)
from detection.infrastructure.tshark.stream_features import (apply_enrollment,
                                                              parse_args)

SECRET = 'test-secret-with-enough-length-0123456789'


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class Clock:
    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now


class CaptureEnrollmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        ca = root / 'ca.crt'
        ca.write_text('PEM-CA\n', encoding='utf-8')
        cls.container = build_container(
            db_path=str(root / 'detection.db'), jwt_secret=SECRET,
            alerts_dir=root / 'alerts', sensor_ttl_minutes=60,
            onboarding=OnboardingConfig(
                agent_endpoint='tls://agent.example.com:8443',
                agent_server_name='agent.example.com', agent_ca_path=ca))
        app = create_app(ApiSettings(root / 'r.json', 'http://o', 'm', 1.0, 'UTC'),
                         container=cls.container)
        port = _free_port()
        cls.server = uvicorn.Server(uvicorn.Config(
            app, host='127.0.0.1', port=port, log_level='error'))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 10
        while not cls.server.started and time.time() < deadline:
            time.sleep(0.05)
        cls.url = f'http://127.0.0.1:{port}'
        token = PyJwtTokenService(SECRET, 15, 60).create_access('user-1')
        cls.user = {'Authorization': f'Bearer {token}'}

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(5)
        cls.tmp.cleanup()

    def setUp(self):
        self.state = tempfile.TemporaryDirectory()
        broker = self._user_post('/api/v1/brokers', {'name': 'b'})
        self.broker_id = broker['id']
        self.key = broker['enrollment_key']

    def tearDown(self):
        self.state.cleanup()

    def _user_post(self, path, body=None):
        import json
        import urllib.request
        request = urllib.request.Request(
            self.url + path, method='POST',
            data=json.dumps(body or {}).encode(),
            headers={**self.user, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    def _credentials(self, key=None, clock=None):
        return SensorCredentials(ApiClient(self.url), self.state.name,
                                 key or self.key, name='host-1',
                                 clock=clock or time.time)

    def test_enroll_persists_state_and_fills_capture_args(self):
        credentials = self._credentials()
        state = credentials.ensure(retry=False)
        self.assertEqual(state.broker_id, self.broker_id)
        self.assertEqual(state.agent_endpoint, 'tls://agent.example.com:8443')
        self.assertEqual(Path(credentials.ca_path).read_text(), 'PEM-CA\n')
        mode = (Path(self.state.name) / 'sensor.json').stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

        args = parse_args(['--enroll-key', self.key, '--api-url', self.url])
        self.assertIsNone(args.endpoint)
        apply_enrollment(args, credentials)
        self.assertEqual(args.endpoint, 'tls://agent.example.com:8443')
        self.assertEqual(args.broker_id, self.broker_id)
        self.assertEqual(args.tls_server_name, 'agent.example.com')
        self.assertEqual(args.tls_ca, credentials.ca_path)

    def test_restart_reuses_identity(self):
        first = self._credentials().ensure(retry=False)
        second = self._credentials().ensure(retry=False)
        self.assertEqual(first.sensor_id, second.sensor_id)
        self.assertEqual(first.sensor_secret, second.sensor_secret)
        self.assertEqual(len(self.container.store.list_sensors(
            'user-1', self.broker_id)), 1)

    def test_token_is_renewed_after_half_lifetime(self):
        clock = Clock()
        credentials = self._credentials(clock=clock)
        credentials.ensure(retry=False)
        original = credentials.token()
        credentials.refresh()
        self.assertEqual(credentials.token(), original)
        clock.now += 31 * 60  # TTL is 60 minutes
        time.sleep(1.1)       # JWT iat has one-second resolution
        credentials.refresh()
        self.assertNotEqual(credentials.token(), original)
        claims = decode_alert_token(credentials.token(), SECRET)
        self.assertEqual(claims['broker_id'], self.broker_id)

    def test_rotation_revokes_and_new_key_reenrolls(self):
        credentials = self._credentials()
        credentials.ensure(retry=False)
        rotated = self._user_post(
            f'/api/v1/brokers/{self.broker_id}/enrollment-key')
        with self.assertRaises(EnrollmentError):
            credentials.refresh()
        self.assertTrue(credentials.revoked.is_set())
        self.assertIsNone(credentials.token())
        with self.assertRaises(EnrollmentError):  # same old key: no re-enroll
            self._credentials().ensure(retry=False)
        fresh = self._credentials(key=rotated['enrollment_key'])
        self.assertEqual(fresh.ensure(retry=False).broker_id, self.broker_id)
        self.assertIsNotNone(fresh.token())

    def test_invalid_key_raises(self):
        with self.assertRaises(EnrollmentError):
            self._credentials(key='ek_' + 'x' * 43).ensure(retry=False)

    def test_network_errors_are_retried(self):
        credentials = SensorCredentials(
            ApiClient(f'http://127.0.0.1:{_free_port()}', timeout=0.5),
            self.state.name, self.key)
        stopper = threading.Timer(1.5, credentials._stop.set)
        stopper.start()
        started = time.time()
        with self.assertRaises(OSError):
            credentials.ensure()
        self.assertGreater(time.time() - started, 1.0)


class RenewingAgentTokenTests(unittest.TestCase):
    def test_reissues_before_expiry(self):
        clock = Clock()
        provider = RenewingAgentToken(SECRET, ttl_minutes=10,
                                      renew_before_seconds=60, clock=clock)
        first = provider()
        self.assertEqual(provider(), first)
        self.assertEqual(decode_alert_token(first, SECRET)['type'], 'agent')
        clock.now += 9 * 60 + 1
        time.sleep(1.1)
        self.assertNotEqual(provider(), first)


if __name__ == '__main__':
    unittest.main()
