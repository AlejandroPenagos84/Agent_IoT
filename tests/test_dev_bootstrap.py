import os
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from detection.http.onboarding import hash_secret
    from detection.infrastructure.dev_bootstrap import main
    from detection.infrastructure.repositories.registry_sqlite import (
        RegistryStore, connect)
except ImportError as exc:  # pyjwt missing
    raise unittest.SkipTest(f'bootstrap dependencies missing: {exc}')

SECRET = 'test-secret-with-enough-length-0123456789'


def _load(path: Path) -> dict[str, str]:
    output = subprocess.run(
        ['sh', '-c', f'. {path} && env'], capture_output=True, text=True,
        check=True, env={}).stdout
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


class DevBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / 'detection.db'
        self.env_file = root / 'bootstrap' / 'dev.env'
        self.environ = dict(os.environ)
        os.environ['AUTH_JWT_SECRET'] = SECRET

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.environ)
        self.tmp.cleanup()

    def _run(self, tenant='user-1'):
        code = main(['--db', str(self.db), '--output', str(self.env_file),
                     '--tenant-id', tenant])
        self.assertEqual(code, 0)
        return _load(self.env_file)

    def _brokers(self, tenant='user-1'):
        connection = connect(str(self.db))
        try:
            return RegistryStore(connection).list_brokers(tenant)
        finally:
            connection.close()

    def test_registers_broker_once_and_reuses_key(self):
        first = self._run()
        second = self._run()
        self.assertTrue(first['ENROLL_KEY'].startswith('ek_'))
        self.assertEqual(first['ENROLL_KEY'], second['ENROLL_KEY'])
        brokers = self._brokers()
        self.assertEqual([b['name'] for b in brokers], ['mosquitto-dev'])
        self.assertEqual(brokers[0]['enrollment_key_hash'],
                         hash_secret(first['ENROLL_KEY']))
        self.assertEqual(first['API_URL'], 'http://report-api:8000')
        self.assertEqual(first['ALERT_API_URL'],
                         'http://report-api:8000/api/v1/alerts')
        self.assertEqual(self.env_file.stat().st_mode & 0o777, 0o600)

    def test_lost_key_is_rotated(self):
        first = self._run()
        self.env_file.with_name('enroll.key').unlink()
        second = self._run()
        self.assertNotEqual(first['ENROLL_KEY'], second['ENROLL_KEY'])
        self.assertEqual(self._brokers()[0]['enrollment_key_hash'],
                         hash_secret(second['ENROLL_KEY']))
        self.assertEqual(len(self._brokers()), 1)

    def test_without_secret_disables_enrollment(self):
        os.environ.pop('AUTH_JWT_SECRET')
        env = self._run()
        self.assertEqual(env['ENROLL_KEY'], '')
        self.assertEqual(env['ALERT_API_URL'], '')
        self.assertEqual(len(self._brokers()), 1)

    def test_empty_tenant_falls_back_to_dev(self):
        self._run(tenant='')
        self.assertEqual(len(self._brokers('dev')), 1)


if __name__ == '__main__':
    unittest.main()
