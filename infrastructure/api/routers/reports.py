"""Natural-language report endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_report_service
from ..report_service import NaturalReportService
from ..schemas import ReportRequest, ReportResponse

router = APIRouter()


def _reference_time(value: str | None) -> str | None:
    # NOTE: not wired into the endpoint yet; ReportRequest.now is currently ignored.
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="now must be a valid ISO-8601 timestamp",
        ) from exc
    if parsed.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail="now must include a timezone",
        )
    return parsed.isoformat()


@router.post("/reports", response_model=ReportResponse)
def generate_natural_report(
    service: Annotated[NaturalReportService, Depends(get_report_service)],
    request: ReportRequest | None = None,
) -> ReportResponse:
    request = request or ReportRequest()
    try:
        natural_report = service.generate(model=request.model)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReportResponse(report=natural_report)
