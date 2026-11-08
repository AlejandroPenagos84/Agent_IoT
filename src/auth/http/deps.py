"""Dependencias FastAPI compartidas por los routers de auth."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from auth.application.errors import (
    AccountDisabled,
    AccountNotVerified,
    InvalidToken,
    RevokedToken,
)
from auth.application.use_cases.login import LoginUseCase
from auth.application.use_cases.logout import Logout
from auth.application.use_cases.refresh_session import RefreshSession
from auth.application.use_cases.register import RegisterUser
from auth.application.use_cases.resend_verification import ResendVerification
from auth.application.use_cases.verify_email import VerifyEmail
from auth.domain.user import User, UserStatus
from auth.http.container import AuthContainer


def get_container(request: Request) -> AuthContainer:
    return request.app.state.container


def get_register(
    container: Annotated[AuthContainer, Depends(get_container)],
) -> RegisterUser:
    return container.register


def get_verify_email(
    container: Annotated[AuthContainer, Depends(get_container)],
) -> VerifyEmail:
    return container.verify_email


def get_resend_verification(
    container: Annotated[AuthContainer, Depends(get_container)],
) -> ResendVerification:
    return container.resend_verification


def get_login(
    container: Annotated[AuthContainer, Depends(get_container)],
) -> LoginUseCase:
    return container.login


def get_refresh_session(
    container: Annotated[AuthContainer, Depends(get_container)],
) -> RefreshSession:
    return container.refresh


def get_logout(
    container: Annotated[AuthContainer, Depends(get_container)],
) -> Logout:
    return container.logout


def get_refresh_token(
    request: Request,
    container: Annotated[AuthContainer, Depends(get_container)],
) -> str:
    token = request.cookies.get(container.cookie_name)
    if not token:
        raise InvalidToken("Refresh token missing")
    return token


def get_optional_refresh_token(
    request: Request,
    container: Annotated[AuthContainer, Depends(get_container)],
) -> str | None:
    return request.cookies.get(container.cookie_name)


def get_current_user(
    container: Annotated[AuthContainer, Depends(get_container)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise InvalidToken("Missing bearer token")

    claims = container.tokens.decode_access(token)
    user = container.users.get_by_id(claims.sub)
    if user is None:
        raise RevokedToken("User no longer exists")

    if user.status is UserStatus.PENDING:
        raise AccountNotVerified("Email not verified")
    if user.status is not UserStatus.ACTIVE:
        raise AccountDisabled("Account disabled")
    return user
