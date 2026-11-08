"""Broker registration endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from detection.http.container import RegistryContainer
from detection.http.onboarding import (ENROLLMENT_PREFIX, hash_secret,
                                       new_secret, sensor_status)
from detection.http.schemas import (BrokerCreate, BrokerCreatedResponse,
                                    BrokerResponse, EnrollmentKeyResponse)
from detection.http.security import get_container, get_current_tenant

router = APIRouter(prefix='/brokers', tags=['brokers'])


def _with_status(container: RegistryContainer, broker: dict) -> dict:
    sensor = container.store.broker_sensor(broker['id'])
    return {**broker,
            'status': sensor_status(sensor, container.onboarding.online_seconds),
            'sensor_id': sensor['id'] if sensor else None,
            'last_seen': sensor.get('last_seen') if sensor else None}


@router.post('', status_code=status.HTTP_201_CREATED,
             response_model=BrokerCreatedResponse)
def create_broker(
    payload: BrokerCreate,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> BrokerCreatedResponse:
    """Register a broker and return the key to install its capture (shown once)."""
    key = new_secret(ENROLLMENT_PREFIX)
    broker = container.store.create_broker(
        tenant_id, payload.name, payload.host, payload.port,
        enrollment_key_hash=hash_secret(key))
    return BrokerCreatedResponse(
        **_with_status(container, broker), enrollment_key=key,
        install_command=container.onboarding.install_command(key))


@router.get('', response_model=list[BrokerResponse])
def list_brokers(
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> list[BrokerResponse]:
    return [BrokerResponse(**_with_status(container, broker))
            for broker in container.store.list_brokers(tenant_id)]


@router.get('/{broker_id}', response_model=BrokerResponse)
def get_broker(
    broker_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> BrokerResponse:
    broker = container.store.get_broker(tenant_id, broker_id)
    if broker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Broker no encontrado')
    return BrokerResponse(**_with_status(container, broker))


@router.post('/{broker_id}/enrollment-key', response_model=EnrollmentKeyResponse)
def rotate_enrollment_key(
    broker_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> EnrollmentKeyResponse:
    """Issue a new key. The old key and the installed capture stop working."""
    key = new_secret(ENROLLMENT_PREFIX)
    if not container.store.set_enrollment_key(tenant_id, broker_id,
                                              hash_secret(key)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Broker no encontrado')
    return EnrollmentKeyResponse(
        enrollment_key=key,
        install_command=container.onboarding.install_command(key))


@router.delete('/{broker_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_broker(
    broker_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> Response:
    if not container.store.delete_broker(tenant_id, broker_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Broker no encontrado')
    return Response(status_code=status.HTTP_204_NO_CONTENT)
