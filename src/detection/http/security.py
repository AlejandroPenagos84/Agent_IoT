"""Authentication dependencies for the detection API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from detection.infrastructure.sensor_tokens import (TokenError, decode_access,
                                                     decode_alert_token)

from .container import RegistryContainer


def get_container(request: Request) -> RegistryContainer:
    return request.app.state.registry


def bearer_token(request: Request) -> str:
    header = request.headers.get('authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Falta el token Bearer')
    return token.strip()


def get_current_tenant(
    request: Request,
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> str:
    """Return the user id (tenant) encoded in a valid access token."""
    if not container.jwt_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail='AUTH_JWT_SECRET no está configurado')
    try:
        payload = decode_access(bearer_token(request), container.jwt_secret)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=str(exc)) from exc
    return str(payload['sub'])


def get_alert_claims(
    request: Request,
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> dict:
    """Validate a sensor or agent token used to ingest alerts."""
    if not container.jwt_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail='AUTH_JWT_SECRET no está configurado')
    try:
        return decode_alert_token(bearer_token(request), container.jwt_secret)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=str(exc)) from exc
