"""Traducción de errores de auth a respuestas HTTP estructuradas."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
from auth.infrastructure.errors import (
    CodeStoreUnavailable,
    DatabaseUnavailable,
    DuplicateRecord,
    RecordNotFound,
)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)

ERROR_MAP: dict[type[AuthError], tuple[int, str]] = {
    InvalidEmail: (422, "INVALID_EMAIL"),
    InvalidUsername: (422, "INVALID_USERNAME"),
    InvalidPassword: (422, "INVALID_PASSWORD"),
    InvalidUserState: (409, "INVALID_USER_STATE"),
    UserNotPending: (409, "USER_NOT_PENDING"),
    UserNotActive: (409, "USER_NOT_ACTIVE"),
    InvalidCredentials: (401, "INVALID_CREDENTIALS"),
    AccountNotVerified: (403, "ACCOUNT_NOT_VERIFIED"),
    AccountDisabled: (403, "ACCOUNT_DISABLED"),
    UserAlreadyExists: (409, "USER_ALREADY_EXISTS"),
    InvalidCode: (400, "INVALID_CODE"),
    TooManyRequests: (429, "TOO_MANY_REQUESTS"),
    InvalidToken: (401, "INVALID_TOKEN"),
    ExpiredToken: (401, "TOKEN_EXPIRED"),
    MalformedToken: (401, "TOKEN_MALFORMED"),
    TokenTypeMismatch: (401, "TOKEN_TYPE_MISMATCH"),
    TokenMissingFamily: (401, "TOKEN_MISSING_FAMILY"),
    RevokedToken: (401, "TOKEN_REVOKED"),
    RefreshTokenReused: (401, "REFRESH_TOKEN_REUSED"),
    DuplicateRecord: (409, "DUPLICATE_RECORD"),
    RecordNotFound: (404, "RECORD_NOT_FOUND"),
    DatabaseUnavailable: (503, "DATABASE_UNAVAILABLE"),
    CodeStoreUnavailable: (503, "CODE_STORE_UNAVAILABLE"),
}


def resolve_error(exc: Exception) -> tuple[int, str]:
    for cls in type(exc).__mro__:
        mapped = ERROR_MAP.get(cls)
        if mapped is not None:
            return mapped
    if isinstance(exc, AuthError):
        return 400, "AUTH_ERROR"
    return 500, "INTERNAL_ERROR"


def _response(status_code: int, code: str, message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


async def auth_error_handler(request: "Request", exc: AuthError):
    status_code, code = resolve_error(exc)
    if status_code >= 500:
        logger.error("Auth infrastructure error", exc_info=(type(exc), exc, exc.__traceback__))
    return _response(status_code, code, str(exc) or code)


async def validation_error_handler(request: "Request", exc: Exception):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse

    errors = getattr(exc, "errors", lambda: [])()
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": jsonable_encoder(errors),
            }
        },
    )


async def unhandled_error_handler(request: "Request", exc: Exception):
    logger.error("Unhandled error", exc_info=(type(exc), exc, exc.__traceback__))
    return _response(500, "INTERNAL_ERROR", "Internal server error")


def register_exception_handlers(app: "FastAPI") -> None:
    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(AuthError, auth_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
