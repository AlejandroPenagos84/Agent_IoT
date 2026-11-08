"""Backward-compatible entrypoint; the API now lives in ``infrastructure.api``.

Kept so ``uvicorn infrastructure.alert_processing.api:app`` keeps working.
"""

from __future__ import annotations

from infrastructure.api.app import create_app
from infrastructure.api.schemas import ReportRequest, ReportResponse

__all__ = ["ReportRequest", "ReportResponse", "app", "create_app"]

app = create_app()
