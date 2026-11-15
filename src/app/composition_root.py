"""Composition root del monolito: construye los módulos y los conecta.

Es el único lugar que conoce a la vez a ``auth`` y a ``detection``. Cada módulo
arma sus propios adaptadores (``build_container``); aquí solo se cruzan:
``detection`` recibe un ``IdentityProvider`` respaldado por la fachada
``auth.api``.

El agente corre en el mismo proceso que la API y guarda las alertas con el
mismo caso de uso ``IngestAlert`` que el endpoint, sin HTTP ni tokens propios.
Solo se arranca cuando ``CAPTURE_ENDPOINT`` está definido.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.background import AgentRunner, RetentionLoop
from auth.api import AuthApi
from auth.http import container as auth_container
from auth.http.errors import register_exception_handlers
from auth.http.routers import auth as auth_routes
from detection.composition_root import AgentConfig, build_agent
from detection.http import container as detection_container
from detection.http.routers import alerts, brokers, health, reports, sensors
from detection.http.settings import ApiSettings
from detection.infrastructure.auth_provider import AuthProvider


@dataclass
class Modules:
    auth: auth_container.AuthContainer
    detection: detection_container.RegistryContainer
    settings: ApiSettings
    agent: AgentRunner | None = None
    retention: RetentionLoop | None = None

    def start(self) -> None:
        for task in (self.agent, self.retention):
            if task is not None:
                task.start()

    def close(self) -> None:
        # Primero el agente: drena alertas hacia la base antes de cerrarla.
        for task in (self.agent, self.retention):
            if task is not None:
                task.stop()
        self.detection.close()
        self.auth.close()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def build_modules(
    *,
    auth: auth_container.AuthContainer | None = None,
    detection_kwargs: dict | None = None,
    settings: ApiSettings | None = None,
    agent_config: AgentConfig | None = None,
) -> Modules:
    """Construye auth, su fachada, detection conectado a ella y el agente."""
    auth = auth or auth_container.build_container()
    identity = AuthProvider(AuthApi(auth.authenticate))
    detection = detection_container.build_container(identity=identity, **(detection_kwargs or {}))
    if agent_config is None and os.getenv('CAPTURE_ENDPOINT'):
        agent_config = AgentConfig.from_env()
    agent = retention = None
    if agent_config is not None:
        cfg = agent_config
        agent = AgentRunner(
            lambda: build_agent(cfg, detection.ingest, detection.sensor_tokens, detection.store),
            wait_for=(cfg.tls_cert, cfg.tls_key)
            if cfg.capture_endpoint.startswith('tls://')
            else (),
        )
        retention = RetentionLoop(
            cfg.evidence_dir,
            _env_int('EVIDENCE_RETENTION_DAYS', 30),
            detection.alerts_dir,
            _env_int('ALERT_RETENTION_DAYS', 0),
        )
    return Modules(
        auth=auth,
        detection=detection,
        settings=settings or ApiSettings.from_env(),
        agent=agent,
        retention=retention,
    )


def create_app(modules: Modules | None = None) -> FastAPI:
    modules = modules or build_modules()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        modules.start()
        try:
            yield
        finally:
            modules.close()

    app = FastAPI(title='AgentIoT', version='1.0.0', lifespan=lifespan)
    # Cada módulo lee su propio estado: auth -> state.container,
    # detection -> state.registry y state.settings.
    app.state.container = modules.auth
    app.state.registry = modules.detection
    app.state.settings = modules.settings

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(auth_routes.router, prefix='/api/v1')
    for router in (
        reports.router,
        brokers.router,
        sensors.broker_router,
        sensors.token_router,
        alerts.router,
    ):
        app.include_router(router, prefix='/api/v1')
    return app
