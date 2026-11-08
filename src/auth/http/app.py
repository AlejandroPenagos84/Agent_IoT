"""Fábrica de la aplicación FastAPI de autenticación."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from auth.http.container import AuthContainer, build_container
from auth.http.errors import register_exception_handlers
from auth.http.routers import auth, health


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        app.state.container.close()


def create_app(*, container: AuthContainer | None = None) -> FastAPI:
    container = container or build_container()
    app = FastAPI(title="Auth API", version="1.0.0", lifespan=_lifespan)
    app.state.container = container
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/v1")
    return app
