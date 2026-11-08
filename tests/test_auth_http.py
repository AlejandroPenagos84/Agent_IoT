import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import jwt  # noqa: F401
    from fastapi.testclient import TestClient

    from auth.http.app import create_app
    from auth.http.container import build_container

    _READY = True
except ImportError:
    _READY = False


class FakeHasher:
    def hash(self, plain): return f"h:{plain}"
    def verify(self, plain, hashed): return hashed == f"h:{plain}"


class FakeCodes:
    def __init__(self): self.codes, self.fails, self.cooling = {}, {}, set()
    def save(self, email, code_hash, ttl_seconds): self.codes[email] = code_hash
    def get(self, email): return self.codes.get(email)
    def delete(self, email): self.codes.pop(email, None); self.fails.pop(email, None)
    def register_failure(self, email):
        self.fails[email] = self.fails.get(email, 0) + 1
        return self.fails[email]
    def try_start_cooldown(self, email, seconds):
        if email in self.cooling:
            return False
        self.cooling.add(email)
        return True


class FakeMail:
    def __init__(self): self.sent = []
    def send(self, to, subject, body): self.sent.append((to, body))
    def last_code(self): return self.sent[-1][1].split(": ")[1].split("\n")[0]


@unittest.skipIf(not _READY, "fastapi/pyjwt/redis/argon2 no instalados")
class AuthHttpTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "AUTH_DB_PATH": ":memory:",
            "AUTH_JWT_SECRET": "s" * 32,
            "AUTH_ACCESS_TTL_MINUTES": "15",
            "AUTH_REFRESH_TTL_MINUTES": "60",
            "AUTH_COOKIE_NAME": "auth_refresh",
            "AUTH_COOKIE_SECURE": "false",
            "AUTH_COOKIE_SAMESITE": "lax",
            "AUTH_COOKIE_PATH": "/api/v1/auth",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

        self.codes, self.mail = FakeCodes(), FakeMail()
        self.container = build_container(
            codes=self.codes,
            mail=self.mail,
            hasher=FakeHasher(),
        )
        self.addCleanup(self.container.close)
        self.client = TestClient(create_app(container=self.container))

    def register(self, email="ana@x.com", username="ana", password="secreto123"):
        return self.client.post("/api/v1/auth/register", json={
            "username": username,
            "email": email,
            "password": password,
        })

    def verify(self, email="ana@x.com"):
        code = self.mail.last_code()
        return self.client.post("/api/v1/auth/verify-email", json={
            "email": email,
            "code": code,
        })

    def login(self, email="ana@x.com", password="secreto123"):
        return self.client.post("/api/v1/auth/login", json={
            "email": email,
            "password": password,
        })

    def activate(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.verify().status_code, 200)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_register_returns_success_dto_without_hash(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["email"], "ana@x.com")
        self.assertEqual(body["status"], "pending")
        self.assertTrue(body["verification_required"])
        self.assertNotIn("hashed_password", body)
        self.assertEqual(self.codes.get("ana@x.com"), f"h:{self.mail.last_code()}")

    def test_verify_email_activates_account(self):
        self.register()
        response = self.verify()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")

    def test_duplicate_registration(self):
        self.activate()
        response = self.register(username="otra")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "USER_ALREADY_EXISTS")

    def test_invalid_verification_code(self):
        self.register()
        response = self.client.post("/api/v1/auth/verify-email", json={
            "email": "ana@x.com",
            "code": "000000",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_CODE")

    def test_pending_account_cannot_login(self):
        self.register()
        response = self.login()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "ACCOUNT_NOT_VERIFIED")

    def test_invalid_credentials(self):
        self.activate()
        response = self.login(password="incorrecta")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "INVALID_CREDENTIALS")

    def test_login_returns_access_and_sets_httponly_cookie(self):
        self.activate()
        response = self.login()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["access_token"])
        self.assertNotIn("refresh_token", body)
        self.assertTrue(response.cookies.get("auth_refresh"))
        self.assertIn("httponly", response.headers["set-cookie"].lower())

    def test_me_requires_bearer(self):
        self.activate()
        access_token = self.login().json()["access_token"]

        ok = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["email"], "ana@x.com")

        missing = self.client.get("/api/v1/auth/me")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["error"]["code"], "INVALID_TOKEN")

    def test_refresh_rotates_cookie(self):
        self.activate()
        self.login()
        first = self.client.cookies.get("auth_refresh")

        response = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["access_token"])
        self.assertNotEqual(first, self.client.cookies.get("auth_refresh"))

    def test_refresh_without_cookie(self):
        response = self.client.post("/api/v1/auth/refresh")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "INVALID_TOKEN")

    def test_logout_clears_cookie_and_invalidates_refresh(self):
        self.activate()
        self.login()

        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.client.cookies.get("auth_refresh"))
        self.assertEqual(self.client.post("/api/v1/auth/refresh").status_code, 401)

    def test_logout_without_cookie_is_idempotent(self):
        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 204)


if __name__ == "__main__":
    unittest.main()
