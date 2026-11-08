"""Alert ingestion and query endpoints."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from detection.http.container import RegistryContainer
from detection.http.schemas import (AlertIngest, AlertIngestResponse,
                                    AlertResponse)
from detection.http.security import (get_alert_claims, get_container,
                                     get_current_tenant)
from detection.http.timeparse import parse_instant

router = APIRouter(prefix='/alerts', tags=['alerts'])
_write_lock = threading.Lock()


def _append_daily(directory: Path, alert: dict) -> None:
    """Append the alert to the same daily JSONL layout the ETL already reads."""
    day = datetime.fromtimestamp(alert['ts'], timezone.utc).date().isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{day}.jsonl'
    with _write_lock, path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(alert, ensure_ascii=False) + '\n')
        handle.flush()


@router.post('', status_code=status.HTTP_201_CREATED,
             response_model=AlertIngestResponse)
def ingest_alert(
    payload: AlertIngest,
    claims: Annotated[dict, Depends(get_alert_claims)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> AlertIngestResponse:
    token_type = claims.get('type')
    if token_type == 'sensor':
        tenant_id = str(claims['tenant_id'])
        broker_id = str(claims['broker_id'])
        sensor_id = str(claims['sensor_id'])
        for field, expected in (('tenant_id', tenant_id),
                                ('broker_id', broker_id),
                                ('sensor_id', sensor_id)):
            value = getattr(payload, field)
            if value is not None and value != expected:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail=f'{field} no coincide con el token')
    else:
        if not payload.tenant_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail='tenant_id es obligatorio para el agente')
        tenant_id = payload.tenant_id
        broker_id = payload.broker_id
        sensor_id = payload.sensor_id
        claim_tenant = claims.get('tenant_id')
        if claim_tenant and claim_tenant != tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail='tenant_id no coincide con el token')
    alert = payload.model_dump()
    alert.update(tenant_id=tenant_id, broker_id=broker_id, sensor_id=sensor_id)
    stored = container.store.add_alert(alert)
    if stored:
        _append_daily(container.alerts_dir, alert)
    return AlertIngestResponse(alert_id=alert['alert_id'], stored=stored)


@router.get('', response_model=list[AlertResponse])
def list_alerts(
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    broker_id: str | None = None,
    sensor_id: str | None = None,
    since: Annotated[str | None, Query(
        description='Inicio inclusivo: epoch o ISO-8601 con zona')] = None,
    until: Annotated[str | None, Query(
        description='Fin exclusivo: epoch o ISO-8601 con zona')] = None,
) -> list[AlertResponse]:
    start = parse_instant(since, 'since')
    end = parse_instant(until, 'until')
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='since debe ser anterior a until')
    return [AlertResponse(**alert) for alert in container.store.list_alerts(
        tenant_id, limit=limit, broker_id=broker_id, sensor_id=sensor_id,
        since=start, until=end)]


@router.get('/{alert_id}', response_model=AlertResponse)
def get_alert(
    alert_id: str,
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    container: Annotated[RegistryContainer, Depends(get_container)],
) -> AlertResponse:
    alert = container.store.get_alert(tenant_id, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Alerta no encontrada')
    return AlertResponse(**alert)
