"""Tareas de fondo del proceso: el agente de detección y la retención.

Ninguna bloquea el arranque de la API:

- ``AgentRunner`` espera (si hace falta) a que existan el certificado y la
  llave TLS, por ejemplo mientras Caddy emite el de Let's Encrypt, y entonces
  construye y arranca el agente.
- ``RetentionLoop`` borra cada cierto tiempo la evidencia y los JSONL diarios
  vencidos.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path

from detection.application import DetectionServer
from detection.reporting.retention import prune_daily_alerts, prune_evidence


def _log(message: str) -> None:
    print(f'[app] {message}', file=sys.stderr, flush=True)


class AgentRunner:
    def __init__(
        self,
        build: Callable[[], DetectionServer],
        wait_for: tuple[str, ...] = (),
        poll_seconds: float = 5.0,
    ):
        self._build = build
        self._wait_for = tuple(path for path in wait_for if path)
        self._poll = poll_seconds
        self._stop = threading.Event()
        self._server: DetectionServer | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name='agent-runner', daemon=True)

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        missing = [p for p in self._wait_for if not Path(p).is_file()]
        if missing:
            _log(f'agente esperando certificados: {", ".join(missing)}')
        while missing:
            if self._stop.wait(self._poll):
                return
            missing = [p for p in self._wait_for if not Path(p).is_file()]
        try:
            server = self._build()
        except Exception as exc:  # noqa: BLE001 - la API sigue viva; se informa
            _log(f'no se pudo construir el agente: {exc}')
            return
        with self._lock:
            if self._stop.is_set():
                server.stop()
                return
            server.start()
            self._server = server
        _log('agente de detección escuchando')

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._server is not None:
                self._server.stop()
        self._thread.join(5.0)


class RetentionLoop:
    def __init__(
        self,
        evidence_dir: str | Path,
        evidence_days: int,
        alerts_dir: str | Path,
        alert_days: int,
        interval_seconds: float = 3600.0,
    ):
        self._args = (Path(evidence_dir), evidence_days, Path(alerts_dir), alert_days)
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='retention', daemon=True)

    def run_once(self) -> tuple[int, int]:
        evidence_dir, evidence_days, alerts_dir, alert_days = self._args
        return (
            len(prune_evidence(evidence_dir, evidence_days)),
            len(prune_daily_alerts(alerts_dir, alert_days)),
        )

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while True:
            try:
                evidence, alerts = self.run_once()
                if evidence or alerts:
                    _log(
                        f'retención: {evidence} carpetas de evidencia y '
                        f'{alerts} archivos de alertas borrados'
                    )
            except OSError as exc:
                _log(f'retención falló: {exc}')
            if self._stop.wait(self._interval):
                return

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(5.0)
