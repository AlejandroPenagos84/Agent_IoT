"""Sensor registration, enrollment and sensor-token endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from detection.http.container import RegistryContainer
from detection.http.onboarding import (SENSOR_SECRET_PREFIX, hash_secret,
                                       new_secret)
from detection.http.schemas import (SensorCreate, SensorEnrollRequest,
                                    SensorEnrollResponse, SensorResponse,
                                    SensorTokenResponse)
from detection.http.security import (bearer_token, get_container,
                                     get_current_tenant)
from detection.infrastructure.repositories.registry_sqlite import (
    SensorExistsError)

broker_router = APIRouter(prefix='/brokers/{broker_id}/sensors',
                          tags=['sensors'])
token_router = APIRouter(prefix='/sensors', tags=['sensors'])

DEFAULT_SENSOR_NAME = 'capture'


def _token_service(container: RegistryContainer):
    if container.sensor_tokens is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail='AUTH_JWT_SECRET no está configurado')
    return container.sensor_tokens


@broker_router.post('', status_code=status.HTTP_201_CREATED,
                    response_model=SensorResponse)
def create_sensor(
    broker_id: str,
    payload: SensorCreate,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> SensorResponse:
    """Admin path. Customers install the capture with the enrollment key."""
    try:
        sensor = container.store.create_sensor(tenant_id, broker_id, payload.name)
    except SensorExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=str(exc)) from exc
    if sensor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Broker no encontrado')
    return SensorResponse(**sensor)


@broker_router.get('', response_model=list[SensorResponse])
def list_sensors(
    broker_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> list[SensorResponse]:
    if container.store.get_broker(tenant_id, broker_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Broker no encontrado')
    return [SensorResponse(**sensor)
            for sensor in container.store.list_sensors(tenant_id, broker_id)]


@token_router.post('/enroll', status_code=status.HTTP_201_CREATED,
                   response_model=SensorEnrollResponse)
def enroll_sensor(
    payload: SensorEnrollRequest,
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> SensorEnrollResponse:
    """Called by the capture on first start with the broker enrollment key.

    Reinstalling with the same key keeps the sensor id and replaces its secret,
    so the previous installation can no longer refresh its token.
    """
    tokens = _token_service(container)
    broker = container.store.broker_by_enrollment_key(
        hash_secret(payload.enrollment_key))
    if broker is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Clave de inscripción inválida o revocada')
    secret = new_secret(SENSOR_SECRET_PREFIX)
    sensor = container.store.enroll_sensor(
        broker, payload.name or DEFAULT_SENSOR_NAME, hash_secret(secret))
    token, expires_in = tokens.create(broker['tenant_id'], broker['id'],
                                      sensor['id'])
    onboarding = container.onboarding
    return SensorEnrollResponse(
        access_token=token, expires_in=expires_in,
        tenant_id=broker['tenant_id'], broker_id=broker['id'],
        sensor_id=sensor['id'], sensor_secret=secret,
        agent_endpoint=onboarding.agent_endpoint,
        agent_server_name=onboarding.agent_server_name,
        agent_ca=onboarding.agent_ca(),
        refresh_interval_seconds=onboarding.refresh_seconds)


@token_router.post('/token/refresh', response_model=SensorTokenResponse)
def refresh_sensor_token(
    request: Request,
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> SensorTokenResponse:
    """Exchange the sensor secret (Bearer) for a fresh token; also a heartbeat."""
    tokens = _token_service(container)
    sensor = container.store.sensor_by_secret(hash_secret(bearer_token(request)))
    if sensor is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Sensor revocado o reemplazado')
    container.store.touch_sensor(sensor['id'])
    token, expires_in = tokens.create(sensor['tenant_id'], sensor['broker_id'],
                                      sensor['id'])
    return SensorTokenResponse(access_token=token, expires_in=expires_in)


@token_router.post('/{sensor_id}/token', response_model=SensorTokenResponse)
def issue_sensor_token(
    sensor_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> SensorTokenResponse:
    sensor = container.store.get_sensor(tenant_id, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Sensor no encontrado')
    token, expires_in = _token_service(container).create(
        tenant_id, sensor['broker_id'], sensor_id)
    return SensorTokenResponse(access_token=token, expires_in=expires_in)
