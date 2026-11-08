import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.application import errors as app_errors
from auth.application.errors import (
    AccountDisabled,
    AccountNotVerified,
    ExpiredToken,
    InvalidCode,
    InvalidCredentials,
    InvalidToken,
    MalformedToken,
    RefreshTokenReused,
    RevokedToken,
    TokenMissingFamily,
    TokenTypeMismatch,
    TooManyRequests,
    UserAlreadyExists,
)
from auth.domain.errors import (
    InvalidEmail,
    InvalidPassword,
    InvalidUserState,
    InvalidUsername,
    UserNotActive,
    UserNotPending,
)
from auth.errors import AuthError
from auth.http.errors import ERROR_MAP, resolve_error
from auth.infrastructure.errors import (
    CodeStoreUnavailable,
    DatabaseUnavailable,
    DuplicateRecord,
    RecordNotFound,
)


class ErrorMappingTests(unittest.TestCase):
    def test_map_entries_are_complete(self):
        for error_cls, (status_code, code) in ERROR_MAP.items():
            self.assertTrue(issubclass(error_cls, AuthError))
            self.assertIsInstance(status_code, int)
            self.assertTrue(code.isupper())

    def test_specific_mappings(self):
        cases = [
            (InvalidEmail("bad"), 422, "INVALID_EMAIL"),
            (InvalidUsername("bad"), 422, "INVALID_USERNAME"),
            (InvalidPassword("bad"), 422, "INVALID_PASSWORD"),
            (InvalidUserState("bad"), 409, "INVALID_USER_STATE"),
            (UserNotPending("bad"), 409, "USER_NOT_PENDING"),
            (UserNotActive("bad"), 409, "USER_NOT_ACTIVE"),
            (InvalidCredentials("bad"), 401, "INVALID_CREDENTIALS"),
            (AccountNotVerified("bad"), 403, "ACCOUNT_NOT_VERIFIED"),
            (AccountDisabled("bad"), 403, "ACCOUNT_DISABLED"),
            (UserAlreadyExists("bad"), 409, "USER_ALREADY_EXISTS"),
            (InvalidCode("bad"), 400, "INVALID_CODE"),
            (TooManyRequests("bad"), 429, "TOO_MANY_REQUESTS"),
            (InvalidToken("bad"), 401, "INVALID_TOKEN"),
            (ExpiredToken("bad"), 401, "TOKEN_EXPIRED"),
            (MalformedToken("bad"), 401, "TOKEN_MALFORMED"),
            (TokenTypeMismatch("bad"), 401, "TOKEN_TYPE_MISMATCH"),
            (TokenMissingFamily("bad"), 401, "TOKEN_MISSING_FAMILY"),
            (RevokedToken("bad"), 401, "TOKEN_REVOKED"),
            (RefreshTokenReused("bad"), 401, "REFRESH_TOKEN_REUSED"),
            (DuplicateRecord("bad"), 409, "DUPLICATE_RECORD"),
            (RecordNotFound("bad"), 404, "RECORD_NOT_FOUND"),
            (DatabaseUnavailable("bad"), 503, "DATABASE_UNAVAILABLE"),
            (CodeStoreUnavailable("bad"), 503, "CODE_STORE_UNAVAILABLE"),
        ]
        for exc, expected_status, expected_code in cases:
            self.assertEqual(resolve_error(exc), (expected_status, expected_code))

    def test_unknown_auth_error_falls_back_to_400(self):
        class UnknownError(AuthError):
            pass

        self.assertEqual(resolve_error(UnknownError("bad")), (400, "AUTH_ERROR"))

    def test_unexpected_error_falls_back_to_500(self):
        self.assertEqual(resolve_error(ValueError("bad")), (500, "INTERNAL_ERROR"))


class CompatibilityTests(unittest.TestCase):
    def test_existing_names_are_still_exported(self):
        for name in ("InvalidCredentials", "AccountNotVerified", "AccountDisabled",
                     "UserAlreadyExists", "InvalidCode", "TooManyRequests", "InvalidToken"):
            self.assertTrue(hasattr(app_errors, name))

    def test_token_errors_are_invalid_token(self):
        for error_cls in (ExpiredToken, MalformedToken, TokenTypeMismatch, TokenMissingFamily):
            self.assertTrue(issubclass(error_cls, InvalidToken))


try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None


@unittest.skipIf(pyjwt is None, "pyjwt no instalado")
class JwtErrorTests(unittest.TestCase):
    SECRET = "s" * 32

    def service(self, access_ttl=15):
        from auth.infrastructure.PyJwtTokenService import PyJwtTokenService

        return PyJwtTokenService(self.SECRET, access_ttl=access_ttl, refresh_ttl=60)

    def test_expired_token(self):
        token = self.service(access_ttl=-1).create_access("u1")
        with self.assertRaises(ExpiredToken) as ctx:
            self.service().decode_access(token)
        self.assertIsInstance(ctx.exception, InvalidToken)

    def test_wrong_token_type(self):
        refresh = self.service().create_refresh("u1", "fam1")
        with self.assertRaises(TokenTypeMismatch) as ctx:
            self.service().decode_access(refresh.token)
        self.assertIsInstance(ctx.exception, InvalidToken)

    def test_tampered_token(self):
        token = self.service().create_access("u1")
        with self.assertRaises(MalformedToken) as ctx:
            self.service().decode_access(token + "x")
        self.assertIsInstance(ctx.exception, InvalidToken)

    def test_bad_signature(self):
        token = self.service().create_access("u1")
        other = type(self.service())(("x" * 32), access_ttl=15, refresh_ttl=60)
        with self.assertRaises(MalformedToken):
            other.decode_access(token)

    def test_refresh_without_family(self):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "u1",
            "jti": "j1",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        }
        token = pyjwt.encode(payload, self.SECRET, algorithm="HS256")
        with self.assertRaises(TokenMissingFamily) as ctx:
            self.service().decode_refresh(token)
        self.assertIsInstance(ctx.exception, InvalidToken)


class SqliteErrorTests(unittest.TestCase):
    def setUp(self):
        from auth.domain.user import User
        from auth.infrastructure.repositories.UserRepositorySqlite import UserRepositorySQLite
        from auth.infrastructure.repositories.sqlite_schema import connect

        self.conn = connect(":memory:")
        self.users = UserRepositorySQLite(self.conn)
        self.user = User(id="u1", username="ana", email="ana@x.com", hashed_password="h")
        self.users.save(self.user)

    def tearDown(self):
        self.conn.close()

    def test_duplicate_username(self):
        from auth.domain.user import User

        with self.assertRaises(DuplicateRecord):
            self.users.save(User(id="u2", username="ana", email="otra@x.com",
                                 hashed_password="h"))

    def test_duplicate_email(self):
        from auth.domain.user import User

        with self.assertRaises(DuplicateRecord):
            self.users.save(User(id="u2", username="otra", email="ana@x.com",
                                 hashed_password="h"))

    def test_update_missing_user(self):
        with self.assertRaises(RecordNotFound):
            self.users.update(replace(self.user, id="missing"))

    def test_delete_missing_user(self):
        with self.assertRaises(RecordNotFound):
            self.users.delete("missing")

    def test_closed_database_is_unavailable(self):
        self.conn.close()
        with self.assertRaises(DatabaseUnavailable):
            self.users.get_by_id("u1")

    def test_refresh_store_duplicate(self):
        from auth.infrastructure.repositories.RefreshTokenStoreSQLite import (
            RefreshTokenStoreSQLite,
        )

        store = RefreshTokenStoreSQLite(self.conn)
        expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        store.save("j1", "u1", "f1", expires_at)
        with self.assertRaises(DuplicateRecord):
            store.save("j1", "u1", "f1", expires_at)


try:
    import redis
except ImportError:
    redis = None


@unittest.skipIf(redis is None, "redis no instalado")
class RedisErrorTests(unittest.TestCase):
    class BrokenClient:
        def get(self, key):
            raise redis.RedisError("down")

    def test_unavailable_store(self):
        from auth.infrastructure.repositories.VerificationCodeStoreRedis import (
            RedisVerificationCodeStore,
        )

        store = RedisVerificationCodeStore(self.BrokenClient())
        with self.assertRaises(CodeStoreUnavailable):
            store.get("ana@x.com")


try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:
    FastAPI = TestClient = None


@unittest.skipIf(FastAPI is None, "fastapi no instalado")
class HttpErrorHandlerTests(unittest.TestCase):
    def client(self):
        from auth.http.errors import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/invalid")
        def invalid():
            raise InvalidCredentials("Invalid username or password")

        @app.get("/db")
        def db():
            raise DatabaseUnavailable("Database is unavailable")

        @app.get("/boom")
        def boom():
            raise RuntimeError("secret internal detail")

        return TestClient(app, raise_server_exceptions=False)

    def test_auth_error_response(self):
        response = self.client().get("/invalid")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {
            "error": {
                "code": "INVALID_CREDENTIALS",
                "message": "Invalid username or password",
            }
        })

    def test_infrastructure_error_status(self):
        response = self.client().get("/db")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "DATABASE_UNAVAILABLE")

    def test_unhandled_error_hides_details(self):
        response = self.client().get("/boom")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret", response.text)


if __name__ == "__main__":
    unittest.main()
