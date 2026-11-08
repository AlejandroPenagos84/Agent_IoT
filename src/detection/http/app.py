"""FastAPI application factory for the report API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .routers import health, reports
from .settings import ApiSettings


def create_app(
    settings: ApiSettings | None = None,
    *,
    summaries_dir: str | Path | None = None,
    report_path: str | Path | None = None,
    ollama_url: str | None = None,
    default_model: str | None = None,
    timeout: float | None = None,
) -> FastAPI:
    """Create the report API using environment-backed production defaults."""
    app = FastAPI(title="IoT Natural Report API", version="1.0.0")
    app.state.settings = settings or ApiSettings.from_env(
        summaries_dir=summaries_dir,
        report_path=report_path,
        ollama_url=ollama_url,
        default_model=default_model,
        timeout=timeout,
    )
    app.include_router(health.router)
    app.include_router(reports.router, prefix="/api/v1")
    return app
