"""Tenant-scoped report endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_report_service
from ..report_service import ScopedReportService
from ..schemas import ReportRequest, ReportResponse
from ..security import get_current_tenant
from ..timeparse import parse_instant

router = APIRouter(tags=["reports"])


def _reference_time(value: str | None) -> datetime | None:
    instant = parse_instant(value, "now")
    if instant is None:
        return None
    return datetime.fromtimestamp(instant, timezone.utc)


def _analytical(service: ScopedReportService, tenant_id: str,
                broker_id: str | None, now: str | None) -> dict[str, Any]:
    try:
        return service.analytical(
            tenant_id, broker_id=broker_id, now=_reference_time(now))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=str(exc)) from exc


@router.get("/reports/analytics")
def get_analytical_report(
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    service: Annotated[ScopedReportService, Depends(get_report_service)],
    broker_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return the JSON report for the caller's alerts, without Ollama."""
    return _analytical(service, tenant_id, broker_id, now)


@router.post("/reports", response_model=ReportResponse)
def generate_natural_report(
    tenant_id: Annotated[str, Depends(get_current_tenant)],
    service: Annotated[ScopedReportService, Depends(get_report_service)],
    request: ReportRequest | None = None,
) -> ReportResponse:
    request = request or ReportRequest()
    analytical = _analytical(service, tenant_id, request.broker_id, request.now)
    try:
        natural_report = service.natural(analytical, model=request.model)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=str(exc)) from exc
    return ReportResponse(report=natural_report)
