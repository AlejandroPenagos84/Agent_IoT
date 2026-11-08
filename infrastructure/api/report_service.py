"""Load the analytical report and turn it into a natural-language report."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.alert_processing.ollama import generate_report


class NaturalReportService:
    """Read report.json from disk and ask Ollama for the narrative report.

    Raises FileNotFoundError or ValueError when the analytical report is
    missing or invalid, and RuntimeError when Ollama fails.
    """

    def __init__(
        self,
        *,
        report_path: Path,
        ollama_url: str,
        default_model: str,
        timeout: float,
    ) -> None:
        self._report_path = report_path
        self._ollama_url = ollama_url
        self._default_model = default_model
        self._timeout = timeout

    def generate(self, model: str | None = None) -> str:
        if not self._report_path.is_file():
            raise FileNotFoundError(
                f"Analytical report does not exist: {self._report_path}"
            )
        analytical_report = json.loads(
            self._report_path.read_text(encoding="utf-8")
        )
        if not isinstance(analytical_report, dict):
            raise ValueError("Analytical report must contain a JSON object")
        return generate_report(
            analytical_report,
            base_url=self._ollama_url,
            model=model or self._default_model,
            timeout=self._timeout,
            print_stream=False,
        )
