"""Runtime settings for the report HTTP API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApiSettings:
    """Resolved configuration shared by the API routers."""

    report_path: Path
    ollama_url: str
    ollama_model: str
    ollama_timeout: float

    @classmethod
    def from_env(
        cls,
        *,
        summaries_dir: str | Path | None = None,
        report_path: str | Path | None = None,
        ollama_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
    ) -> "ApiSettings":
        """Build settings from explicit overrides, falling back to environment."""
        if report_path is None and summaries_dir is not None:
            report_path = Path(summaries_dir).parent / "report.json"
        return cls(
            report_path=Path(report_path or os.getenv(
                "REPORT_PATH", "/processed/report.json")),
            ollama_url=ollama_url or os.getenv(
                "OLLAMA_BASE_URL", "http://ollama:11434"),
            ollama_model=default_model or os.getenv("OLLAMA_MODEL", "gemma3:4b"),
            ollama_timeout=timeout or float(os.getenv("OLLAMA_TIMEOUT", "300")),
        )
