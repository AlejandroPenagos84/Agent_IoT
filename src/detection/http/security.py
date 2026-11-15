"""Authentication dependencies for the detection API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from detection.application.ports.identity_provider import UnauthenticatedError
from detection.infrastructure.sensor_tokens import TokenError

from .container import RegistryContainer


def get_container(request: Request) -> RegistryContainer:
    return request.app.state.registry


def bearer_token(request: Request) -> str:
    header = request.headers.get('authorization', '')
    scheme, _, token = header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Falta el token Bearer'
        )
    return token.strip()


def get_current_tenant(
    request: Request,
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> str:
    """Return the tenant (user id) of the caller through the IdentityProvider port."""
    if container.identity is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Proveedor de identidad no configurado',
        )
    try:
        return container.identity.get_identity(bearer_token(request))
    except UnauthenticatedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_sensor_claims(
    request: Request,
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> dict:
    """Validate the sensor token of a capture installation."""
    if container.sensor_tokens is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='AUTH_JWT_SECRET no está configurado',
        )
    try:
        return container.sensor_tokens.decode(bearer_token(request))
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
