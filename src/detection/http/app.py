"""FastAPI application factory for the detection API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from .container import RegistryContainer, build_container
from .routers import alerts, brokers, health, reports, sensors
from .settings import ApiSettings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        app.state.registry.close()


def create_app(
    settings: ApiSettings | None = None,
    *,
    container: RegistryContainer | None = None,
    summaries_dir: str | Path | None = None,
    report_path: str | Path | None = None,
    ollama_url: str | None = None,
    default_model: str | None = None,
    timeout: float | None = None,
) -> FastAPI:
    """Create the detection API using environment-backed production defaults."""
    app = FastAPI(title="IoT Detection API", version="1.0.0",
                  lifespan=_lifespan)
    app.state.settings = settings or ApiSettings.from_env(
        summaries_dir=summaries_dir,
        report_path=report_path,
        ollama_url=ollama_url,
        default_model=default_model,
        timeout=timeout,
    )
    app.state.registry = container or build_container()
    app.include_router(health.router)
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(brokers.router, prefix="/api/v1")
    app.include_router(sensors.broker_router, prefix="/api/v1")
    app.include_router(sensors.token_router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    return app
