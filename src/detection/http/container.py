"""Build and inject the detection registry adapters."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from detection.http.onboarding import OnboardingConfig
from detection.infrastructure.repositories.registry_sqlite import (
    RegistryStore,
    connect,
)
from detection.infrastructure.sensor_tokens import SensorTokenService


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class RegistryContainer:
    connection: sqlite3.Connection
    store: RegistryStore
    sensor_tokens: SensorTokenService | None
    jwt_secret: str | None
    alerts_dir: Path
    onboarding: OnboardingConfig = field(default_factory=OnboardingConfig)

    def close(self) -> None:
        self.connection.close()


def build_container(
    *,
    db_path: str | None = None,
    jwt_secret: str | None = None,
    alerts_dir: str | Path | None = None,
    sensor_ttl_minutes: int | None = None,
    onboarding: OnboardingConfig | None = None,
) -> RegistryContainer:
    secret = jwt_secret if jwt_secret is not None else os.getenv("AUTH_JWT_SECRET")
    path = db_path or os.getenv("DETECTION_DB_PATH", ":memory:")
    directory = Path(alerts_dir or os.getenv("ALERTS_DIR", "/alerts"))
    ttl = sensor_ttl_minutes if sensor_ttl_minutes is not None else _env_int(
        "SENSOR_TOKEN_TTL_MINUTES", 1440)
    connection = connect(path)
    return RegistryContainer(
        connection=connection,
        store=RegistryStore(connection),
        sensor_tokens=SensorTokenService(secret, ttl) if secret else None,
        jwt_secret=secret,
        alerts_dir=directory,
        onboarding=onboarding or OnboardingConfig.from_env(),
    )
