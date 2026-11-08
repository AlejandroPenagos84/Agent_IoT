import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.application.errors import (AccountNotVerified, InvalidCode, InvalidCredentials,
                                     InvalidToken, TooManyRequests, UserAlreadyExists)
from auth.application.use_cases.login import LoginUseCase
from auth.application.use_cases.register import RegisterUser
from auth.application.use_cases.resend_verification import ResendVerification
from auth.application.use_cases.send_verification_code import MAX_ATTEMPTS, SendVerificationCode
from auth.application.use_cases.verify_email import VerifyEmail
from auth.domain.user import User, UserStatus


class FakeHasher:
    def hash(self, plain): return f"h:{plain}"
    def verify(self, plain, hashed): return hashed == f"h:{plain}"


class FakeUsers:
    def __init__(self): self.by_id = {}
    def get_by_username(self, u): return next((x for x in self.by_id.values() if x.username == u), None)
    def get_by_email(self, e): return next((x for x in self.by_id.values() if x.email == e), None)
    def get_by_id(self, i): return self.by_id.get(i)
    def save(self, user): self.by_id[user.id] = user
    def update(self, user): self.by_id[user.id] = user
    def delete(self, i): self.by_id.pop(i, None)


class FakeCodes:
    def __init__(self): self.codes, self.fails, self.cooling = {}, {}, set()
    def save(self, e, h, ttl_seconds): self.codes[e] = h
    def get(self, e): return self.codes.get(e)
    def delete(self, e): self.codes.pop(e, None); self.fails.pop(e, None)
    def register_failure(self, e): self.fails[e] = self.fails.get(e, 0) + 1; return self.fails[e]
    def try_start_cooldown(self, e, seconds):
        if e in self.cooling: return False
        self.cooling.add(e); return True


class FakeMail:
    def __init__(self): self.sent = []
    def send(self, to, subject, body): self.sent.append((to, body))
    def last_code(self): return self.sent[-1][1].split(": ")[1].split("\n")[0]


class FakeTokens:
    def __init__(self): self.created = []
    def create_access(self, user_id): return f"access:{user_id}"
    def create_refresh(self, user_id, family_id):
        from datetime import datetime, timezone
        from auth.application.ports.token_service import TokenData
        jti = f"jti-{len(self.created) + 1}"
        self.created.append((user_id, family_id, jti))
        return TokenData(token=f"refresh:{user_id}:{family_id}", jti=jti,
                         expires_at=datetime.now(timezone.utc))
    def decode_access(self, token): raise NotImplementedError
    def decode_refresh(self, token): raise NotImplementedError


class FakeRefreshStore:
    def __init__(self): self.saved = []
    def save(self, jti, user_id, family_id, expires_at):
        self.saved.append((jti, user_id, family_id, expires_at))
    def get(self, jti): return None
    def rotate(self, old_jti, new_jti): return True
    def revoke(self, jti): pass
    def revoke_family(self, family_id): pass


class RegistrationFlowTests(unittest.TestCase):
    def setUp(self):
        self.users, self.codes, self.mail, hasher = FakeUsers(), FakeCodes(), FakeMail(), FakeHasher()
        send = SendVerificationCode(self.codes, hasher, self.mail)
        self.register = RegisterUser(self.users, hasher, send)
        self.verify = VerifyEmail(self.users, self.codes, hasher)
        self.resend = ResendVerification(self.users, send)
        self.login = LoginUseCase(self.users, hasher, FakeTokens(), FakeRefreshStore())

    def test_register_creates_pending_and_sends_6_digit_code(self):
        user = self.register.execute("ana", "ana@x.com", "pw")
        self.assertIs(user.status, UserStatus.PENDING)
        self.assertRegex(self.mail.last_code(), r"^\d{6}$")
        self.assertEqual(self.codes.get("ana@x.com"), f"h:{self.mail.last_code()}")  # guarda el hash

    def test_pending_cannot_login_until_verified(self):
        self.register.execute("ana", "ana@x.com", "pw")
        with self.assertRaises(AccountNotVerified):
            self.login.execute("ana@x.com", "pw")
        active = self.verify.execute("ana@x.com", self.mail.last_code())
        self.assertIs(active.status, UserStatus.ACTIVE)
        pair = self.login.execute("ana@x.com", "pw")
        self.assertTrue(pair.access_token)
        self.assertTrue(pair.refresh_token)
        self.assertIsNone(self.codes.get("ana@x.com"))

    def test_wrong_password_hides_account_state(self):
        self.register.execute("ana", "ana@x.com", "pw")
        with self.assertRaises(InvalidCredentials):
            self.login.execute("ana@x.com", "bad")

    def test_code_invalidated_after_max_attempts(self):
        self.register.execute("ana", "ana@x.com", "pw")
        good = self.mail.last_code()
        for _ in range(MAX_ATTEMPTS):
            with self.assertRaises(InvalidCode):
                self.verify.execute("ana@x.com", "000000" if good != "000000" else "111111")
        with self.assertRaises(InvalidCode):
            self.verify.execute("ana@x.com", good)   # ya se borró

    def test_resend_respects_cooldown_and_replaces_code(self):
        self.register.execute("ana", "ana@x.com", "pw")
        with self.assertRaises(TooManyRequests):
            self.resend.execute("ana@x.com")
        self.codes.cooling.clear()                   # simula que pasaron 60 s
        old = self.mail.last_code()
        self.codes.fails["ana@x.com"] = 3
        self.resend.execute("ana@x.com")
        self.assertEqual(len(self.mail.sent), 2)
        self.assertNotIn("ana@x.com", self.codes.fails)
        if old != self.mail.last_code():
            with self.assertRaises(InvalidCode):
                self.verify.execute("ana@x.com", old)

    def test_resend_silent_for_unknown_or_active(self):
        self.resend.execute("nadie@x.com")
        self.register.execute("ana", "ana@x.com", "pw")
        self.verify.execute("ana@x.com", self.mail.last_code())
        self.codes.cooling.clear()
        self.resend.execute("ana@x.com")
        self.assertEqual(len(self.mail.sent), 1)

    def test_duplicates(self):
        self.register.execute("ana", "ana@x.com", "pw")
        self.verify.execute("ana@x.com", self.mail.last_code())
        with self.assertRaises(UserAlreadyExists):
            self.register.execute("otra", "ana@x.com", "pw")
        with self.assertRaises(UserAlreadyExists):
            self.register.execute("ana", "otro@x.com", "pw")

    def test_pending_reregister_reuses_account(self):
        first = self.register.execute("ana", "ana@x.com", "pw")
        self.codes.cooling.clear()
        second = self.register.execute("ana2", "ana@x.com", "pw2")
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.users.by_id), 1)
        self.assertEqual(self.users.get_by_email("ana@x.com").username, "ana2")


try:
    import argon2  # noqa: F401
    import jwt  # noqa: F401
except ImportError:
    argon2 = jwt = None


@unittest.skipIf(jwt is None or argon2 is None, "pyjwt/argon2-cffi no instalados")
class AdapterTests(unittest.TestCase):
    def test_argon2(self):
        from auth.infrastructure.PasswordHasherArgon2 import PasswordHasherArgon2
        h = PasswordHasherArgon2()
        hashed = h.hash("secreto")
        self.assertTrue(h.verify("secreto", hashed))
        self.assertFalse(h.verify("otro", hashed))
        self.assertFalse(h.verify("secreto", "no-es-hash"))

    def test_jwt_types_and_expiry(self):
        from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
        svc = PyJwtTokenService("s" * 32, access_ttl=15, refresh_ttl=60)
        access = svc.create_access("u1")
        refresh = svc.create_refresh("u1", "fam1")
        self.assertEqual(svc.decode_access(access).sub, "u1")
        claims = svc.decode_refresh(refresh.token)
        self.assertEqual((claims.jti, claims.family_id, claims.exp), (refresh.jti, "fam1", refresh.expires_at))
        with self.assertRaises(InvalidToken):
            svc.decode_access(refresh.token)
        with self.assertRaises(InvalidToken):
            svc.decode_refresh(access)
        with self.assertRaises(InvalidToken):
            PyJwtTokenService("x" * 32, 15, 60).decode_access(access)
        expired = PyJwtTokenService("s" * 32, access_ttl=-1, refresh_ttl=60).create_access("u1")
        with self.assertRaises(InvalidToken):
            svc.decode_access(expired)

    def test_sqlite_repositories(self):
        from datetime import datetime, timedelta, timezone
        from auth.infrastructure.repositories.RefreshTokenStoreSQLite import RefreshTokenStoreSQLite
        from auth.infrastructure.repositories.UserRepositorySqlite import UserRepositorySQLite
        from auth.infrastructure.repositories.sqlite_schema import connect
        conn = connect(":memory:")
        users = UserRepositorySQLite(conn)
        users.save(User(id="u1", username="ana", email="ana@x.com", hashed_password="h"))
        self.assertIs(users.get_by_email("ana@x.com").status, UserStatus.PENDING)
        from dataclasses import replace
        users.update(replace(users.get_by_id("u1"), status=UserStatus.ACTIVE))
        self.assertTrue(users.get_by_username("ana").can_login)

        store = RefreshTokenStoreSQLite(conn)
        exp = datetime.now(timezone.utc) + timedelta(days=7)
        store.save("j1", "u1", "f1", exp)
        self.assertEqual(store.get("j1").expires_at, exp)
        self.assertTrue(store.rotate("j1", "j2"))
        self.assertFalse(store.rotate("j1", "j3"))          # reuso detectado
        store.save("j2", "u1", "f1", exp)
        store.revoke_family("f1")
        self.assertIsNotNone(store.get("j2").revoked_at)


@unittest.skipIf(jwt is None, "pyjwt no instalado")
class RefreshSessionTests(unittest.TestCase):
    def setUp(self):
        from dataclasses import replace
        from auth.application.use_cases.refresh_session import RefreshSession
        from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
        from auth.infrastructure.repositories.RefreshTokenStoreSQLite import RefreshTokenStoreSQLite
        from auth.infrastructure.repositories.UserRepositorySqlite import UserRepositorySQLite
        from auth.infrastructure.repositories.sqlite_schema import connect
        self.replace = replace
        conn = connect(":memory:")
        self.users = UserRepositorySQLite(conn)
        self.store = RefreshTokenStoreSQLite(conn)
        self.tokens = PyJwtTokenService("s" * 32, access_ttl=15, refresh_ttl=60)
        self.user = User(id="u1", username="ana", email="ana@x.com", hashed_password="h",
                         status=UserStatus.ACTIVE)
        self.users.save(self.user)
        self.refresh = RefreshSession(self.tokens, self.users, self.store)
        first = self.tokens.create_refresh("u1", "fam1")
        self.store.save(first.jti, "u1", "fam1", first.expires_at)
        self.first = first

    def test_rotates_and_returns_pair(self):
        pair = self.refresh.execute(self.first.token)
        self.assertEqual(self.tokens.decode_access(pair.access_token).sub, "u1")
        new = self.tokens.decode_refresh(pair.refresh_token)
        self.assertEqual(new.family_id, "fam1")
        self.assertIsNotNone(self.store.get(self.first.jti).revoked_at)
        self.assertIsNone(self.store.get(new.jti).revoked_at)

    def test_reuse_revokes_family(self):
        from auth.application.errors import RefreshTokenReused
        pair = self.refresh.execute(self.first.token)
        with self.assertRaises(RefreshTokenReused):
            self.refresh.execute(self.first.token)          # token viejo robado
        new_jti = self.tokens.decode_refresh(pair.refresh_token).jti
        self.assertIsNotNone(self.store.get(new_jti).revoked_at)  # el legítimo también cae

    def test_unknown_token_is_revoked(self):
        from auth.application.errors import RevokedToken
        orphan = self.tokens.create_refresh("u1", "fam1")   # firmado pero nunca guardado
        with self.assertRaises(RevokedToken):
            self.refresh.execute(orphan.token)

    def test_disabled_and_pending_users(self):
        from auth.application.errors import AccountDisabled, AccountNotVerified
        self.users.update(self.replace(self.user, status=UserStatus.DISABLED))
        with self.assertRaises(AccountDisabled):
            self.refresh.execute(self.first.token)
        self.assertIsNotNone(self.store.get(self.first.jti).revoked_at)

        second = self.tokens.create_refresh("u1", "fam2")
        self.store.save(second.jti, "u1", "fam2", second.expires_at)
        self.users.update(self.replace(self.user, status=UserStatus.PENDING))
        with self.assertRaises(AccountNotVerified):
            self.refresh.execute(second.token)

    def test_access_token_is_rejected(self):
        with self.assertRaises(InvalidToken):
            self.refresh.execute(self.tokens.create_access("u1"))


try:
    import redis
    _r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), decode_responses=True,
                     socket_connect_timeout=0.5)
    _r.ping()
except Exception:
    _r = None


@unittest.skipIf(_r is None, "Redis no disponible")
class RedisStoreTests(unittest.TestCase):
    def test_store(self):
        from auth.infrastructure.repositories.VerificationCodeStoreRedis import RedisVerificationCodeStore
        s, e = RedisVerificationCodeStore(_r), f"t{time.time_ns()}@x.com"
        s.save(e, "hash", 60)
        self.assertEqual(s.get(e), "hash")
        self.assertEqual([s.register_failure(e), s.register_failure(e)], [1, 2])
        self.assertTrue(s.try_start_cooldown(e, 60))
        self.assertFalse(s.try_start_cooldown(e, 60))
        s.delete(e)
        self.assertIsNone(s.get(e))
        self.assertEqual(s.register_failure(e), 1)
        _r.delete(f"verify_cooldown:{e}", f"verify_fail:{e}")


if __name__ == "__main__":
    unittest.main()
