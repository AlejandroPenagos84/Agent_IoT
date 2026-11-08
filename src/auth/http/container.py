"""Construcción e inyección de adaptadores y casos de uso de auth."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

import redis

from auth.application.ports.mail_sender import MailSender
from auth.application.ports.password_hasher import PasswordHasher
from auth.application.ports.refresh_store import RefreshTokenStore
from auth.application.ports.token_service import TokenService
from auth.application.ports.user_repository import UserRepository
from auth.application.ports.verification_code_store import VerificationCodeStore
from auth.application.use_cases.login import LoginUseCase
from auth.application.use_cases.logout import Logout
from auth.application.use_cases.refresh_session import RefreshSession
from auth.application.use_cases.register import RegisterUser
from auth.application.use_cases.resend_verification import ResendVerification
from auth.application.use_cases.send_verification_code import SendVerificationCode
from auth.application.use_cases.verify_email import VerifyEmail
from auth.infrastructure.MailSenderSMTP import MailSenderSMTP
from auth.infrastructure.PasswordHasherArgon2 import PasswordHasherArgon2
from auth.infrastructure.PyJwtTokenService import PyJwtTokenService
from auth.infrastructure.repositories.RefreshTokenStoreSQLite import RefreshTokenStoreSQLite
from auth.infrastructure.repositories.UserRepositorySqlite import UserRepositorySQLite
from auth.infrastructure.repositories.VerificationCodeStoreRedis import (
    RedisVerificationCodeStore,
)
from auth.infrastructure.repositories.sqlite_schema import connect


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AuthContainer:
    db_connection: sqlite3.Connection
    users: UserRepository
    codes: VerificationCodeStore
    hasher: PasswordHasher
    mail: MailSender
    tokens: TokenService
    refresh_store: RefreshTokenStore
    register: RegisterUser
    verify_email: VerifyEmail
    resend_verification: ResendVerification
    login: LoginUseCase
    refresh: RefreshSession
    logout: Logout
    access_ttl_minutes: int
    refresh_ttl_minutes: int
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    cookie_path: str

    def close(self) -> None:
        self.db_connection.close()


def build_container(
    *,
    codes: VerificationCodeStore | None = None,
    mail: MailSender | None = None,
    hasher: PasswordHasher | None = None,
) -> AuthContainer:
    secret = os.getenv("AUTH_JWT_SECRET")
    if not secret:
        raise ValueError("AUTH_JWT_SECRET is required")

    access_ttl_minutes = _env_int("AUTH_ACCESS_TTL_MINUTES", 15)
    refresh_ttl_minutes = _env_int("AUTH_REFRESH_TTL_MINUTES", 10080)

    connection = connect(os.getenv("AUTH_DB_PATH", "/data/auth.db"))
    users = UserRepositorySQLite(connection)
    hasher = hasher or PasswordHasherArgon2()
    codes = codes or RedisVerificationCodeStore(
        redis.Redis(
            host=os.getenv("AUTH_REDIS_HOST", "redis"),
            port=_env_int("AUTH_REDIS_PORT", 6379),
            db=_env_int("AUTH_REDIS_DB", 0),
            password=os.getenv("AUTH_REDIS_PASSWORD") or None,
            decode_responses=True,
        )
    )
    mail = mail or MailSenderSMTP(
        os.getenv("AUTH_SMTP_HOST", "localhost"),
        _env_int("AUTH_SMTP_PORT", 587),
        os.getenv("AUTH_SMTP_USERNAME", ""),
        os.getenv("AUTH_SMTP_PASSWORD", ""),
        use_tls=_env_bool("AUTH_SMTP_TLS", True),
        use_auth=_env_bool("AUTH_SMTP_AUTH", True),
        from_address=os.getenv("AUTH_SMTP_FROM") or None,
    )
    tokens = PyJwtTokenService(secret, access_ttl_minutes, refresh_ttl_minutes)
    refresh_store = RefreshTokenStoreSQLite(connection)
    send_code = SendVerificationCode(codes, hasher, mail)

    return AuthContainer(
        db_connection=connection,
        users=users,
        codes=codes,
        hasher=hasher,
        mail=mail,
        tokens=tokens,
        refresh_store=refresh_store,
        register=RegisterUser(users, hasher, send_code),
        verify_email=VerifyEmail(users, codes, hasher),
        resend_verification=ResendVerification(users, send_code),
        login=LoginUseCase(users, hasher, tokens, refresh_store),
        refresh=RefreshSession(tokens, users, refresh_store),
        logout=Logout(tokens, refresh_store),
        access_ttl_minutes=access_ttl_minutes,
        refresh_ttl_minutes=refresh_ttl_minutes,
        cookie_name=os.getenv("AUTH_COOKIE_NAME", "auth_refresh"),
        cookie_secure=_env_bool("AUTH_COOKIE_SECURE", True),
        cookie_samesite=os.getenv("AUTH_COOKIE_SAMESITE", "lax"),
        cookie_path=os.getenv("AUTH_COOKIE_PATH", "/api/v1/auth"),
    )
