"""detection autentica a través de auth.api en la app única del monolito."""

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from app.composition_root import build_modules, create_app
    from auth.domain.user import UserStatus
    from auth.http.container import build_container
    from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
    from detection.http.settings import ApiSettings
    from test_auth_http import FakeCodes, FakeHasher, FakeMail
except ImportError as exc:
    raise unittest.SkipTest(f'API test dependencies missing: {exc}') from exc

SECRET = 's' * 32


class AppIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'AUTH_DB_PATH': ':memory:', 'AUTH_JWT_SECRET': SECRET})
        env.start()
        self.addCleanup(env.stop)
        self.mail = FakeMail()
        auth = build_container(codes=FakeCodes(), mail=self.mail, hasher=FakeHasher())
        modules = build_modules(
            auth=auth,
            detection_kwargs={
                'db_path': str(root / 'detection.db'),
                'jwt_secret': SECRET,
                'alerts_dir': root / 'alerts',
            },
            settings=ApiSettings(root / 'r.json', 'http://o', 'm', 1.0, 'UTC'),
        )
        self.users = auth.users
        self.client = TestClient(create_app(modules))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def _login(self):
        self.client.post(
            '/api/v1/auth/register',
            json={'username': 'ana', 'email': 'ana@x.com', 'password': 'secreto123'},
        )
        self.client.post(
            '/api/v1/auth/verify-email', json={'email': 'ana@x.com', 'code': self.mail.last_code()}
        )
        response = self.client.post(
            '/api/v1/auth/login', json={'email': 'ana@x.com', 'password': 'secreto123'}
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['access_token']

    @staticmethod
    def _bearer(token):
        return {'Authorization': f'Bearer {token}'}

    def test_active_user_reaches_detection_as_its_tenant(self):
        token = self._login()
        created = self.client.post(
            '/api/v1/brokers', json={'name': 'b'}, headers=self._bearer(token)
        )
        self.assertEqual(created.status_code, 201)
        me = self.client.get('/api/v1/auth/me', headers=self._bearer(token))
        self.assertEqual(created.json()['tenant_id'], me.json()['id'])

    def test_disabled_user_is_rejected_by_detection(self):
        token = self._login()
        user = self.users.get_by_email('ana@x.com')
        self.users.update(replace(user, status=UserStatus.DISABLED))
        response = self.client.get('/api/v1/brokers', headers=self._bearer(token))
        self.assertEqual(response.status_code, 401)

    def test_valid_jwt_of_unknown_user_is_rejected(self):
        token = PyJwtTokenService(SECRET, 15, 60).create_access('ghost')
        response = self.client.get('/api/v1/brokers', headers=self._bearer(token))
        self.assertEqual(response.status_code, 401)

    def test_garbage_token_is_401(self):
        response = self.client.get('/api/v1/brokers', headers=self._bearer('x.y.z'))
        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
