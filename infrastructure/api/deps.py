"""FastAPI dependencies shared by the routers."""

from __future__ import annotations

from fastapi import Request

from .report_service import NaturalReportService
from .settings import ApiSettings


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


def get_report_service(request: Request) -> NaturalReportService:
    settings = get_settings(request)
    return NaturalReportService(
        report_path=settings.report_path,
        ollama_url=settings.ollama_url,
        default_model=settings.ollama_model,
        timeout=settings.ollama_timeout,
    )
