"""Alert ingestion and query endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from detection.domain.model import Alert
from detection.http.container import RegistryContainer
from detection.http.schemas import AlertIngest, AlertIngestResponse, AlertResponse
from detection.http.security import get_container, get_current_tenant, get_sensor_claims
from detection.http.timeparse import parse_instant

router = APIRouter(prefix='/alerts', tags=['alerts'])
IDENTITY = ('tenant_id', 'broker_id', 'sensor_id')


@router.post('', status_code=status.HTTP_201_CREATED, response_model=AlertIngestResponse)
def ingest_alert(
    payload: AlertIngest,
    claims: Annotated[dict, Depends(get_sensor_claims)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> AlertIngestResponse:
    """Ingest an alert on behalf of a sensor. The agent ingests in-process."""
    for field in IDENTITY:
        value = getattr(payload, field)
        if value is not None and value != str(claims[field]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f'{field} no coincide con el token'
            )
    data = payload.model_dump()
    data.update({field: str(claims[field]) for field in IDENTITY})
    stored = container.ingest.execute(Alert(**data))
    return AlertIngestResponse(alert_id=payload.alert_id, stored=stored)


@router.get('', response_model=list[AlertResponse])
def list_alerts(
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    broker_id: str | None = None,
    sensor_id: str | None = None,
    since: Annotated[
        str | None, Query(description='Inicio inclusivo: epoch o ISO-8601 con zona')
    ] = None,
    until: Annotated[
        str | None, Query(description='Fin exclusivo: epoch o ISO-8601 con zona')
    ] = None,
) -> list[AlertResponse]:
    start = parse_instant(since, 'since')
    end = parse_instant(until, 'until')
    if start is not None and end is not None and start >= end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='since debe ser anterior a until'
        )
    return [
        AlertResponse(**alert)
        for alert in container.store.list_alerts(
            tenant_id, limit=limit, broker_id=broker_id, sensor_id=sensor_id, since=start, until=end
        )
    ]


@router.get('/{alert_id}', response_model=AlertResponse)
def get_alert(
    alert_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> AlertResponse:
    alert = container.store.get_alert(tenant_id, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Alerta no encontrada')
    return AlertResponse(**alert)
