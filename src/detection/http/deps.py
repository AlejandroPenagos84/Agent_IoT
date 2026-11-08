"""FastAPI dependencies shared by the routers."""

from __future__ import annotations

from fastapi import Request

from .report_service import ScopedReportService
from .settings import ApiSettings


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_report_service(request: Request) -> ScopedReportService:
    settings = get_settings(request)
    return ScopedReportService(
        store=request.app.state.registry.store,
        ollama_url=settings.ollama_url,
        default_model=settings.ollama_model,
        timeout=settings.ollama_timeout,
        output_timezone=settings.report_timezone,
    )
