"""Credenciales del sensor para la conexión con el agente.

Flujo:

1. Primer arranque: ``EnrollSensor`` hace ``POST /api/v1/sensors/enroll`` con
   ``ENROLL_KEY``. La identidad, el secreto y la CA del agente quedan en
   ``/state``, así un reinicio no crea otra instalación.
2. Cada ``refresh_interval_seconds``: ``RefreshSensorToken`` hace
   ``POST /api/v1/sensors/token/refresh`` con el secreto. Es el heartbeat y, si
   el token pasó la mitad de su vida, el nuevo se usa en la siguiente conexión.
3. Un ``401`` en el refresh significa que el sensor fue revocado o reinstalado
   en otro equipo: se deja de enviar y no se re-inscribe con la misma clave.
   Una clave nueva sí re-inscribe.

``SensorCredentials`` arma los casos de uso y aporta lo que es de
infraestructura: reintentos de red con backoff y el hilo del heartbeat.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from capture.application.errors import EnrollmentError
from capture.application.ports.enrollment_api import EnrollmentApi
from capture.application.ports.sensor_state_store import SensorStateStore
from capture.application.use_cases.enroll_sensor import EnrollSensor
from capture.application.use_cases.refresh_sensor_token import RefreshSensorToken
from capture.domain.sensor_state import SensorState
from capture.infrastructure.enrollment.file_state_store import FileSensorStateStore

MAX_BACKOFF = 60.0
MIN_REFRESH_INTERVAL = 5
NETWORK_ERRORS = (OSError, ValueError, KeyError)


def _log(message: str) -> None:
    print(f'[enroll] {message}', file=sys.stderr, flush=True)


class SensorCredentials:
    """Identidad del sensor y un token válido para conectar con el agente."""

    def __init__(
        self,
        api: EnrollmentApi,
        state_dir: str | Path,
        enrollment_key: str,
        name: str | None = None,
        clock: Callable[[], float] = time.time,
        store: SensorStateStore | None = None,
    ):
        self.enrollment_key = enrollment_key
        self.name = name or socket.gethostname()
        self.store = store or FileSensorStateStore(state_dir)
        self.state: SensorState | None = None
        self.revoked = threading.Event()

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._refresh = RefreshSensorToken(api, self.store, clock=clock, lock=self._lock)
        self._enroll = EnrollSensor(api, self.store, self._refresh, clock=clock, log=_log)

    @property
    def ca_path(self) -> str | None:
        return self.store.ca_path

    # ---- casos de uso ------------------------------------------------------
    def ensure(self, retry: bool = True) -> SensorState:
        """Carga o crea las credenciales, reintentando los errores de red.

        Lanza ``EnrollmentError`` si la clave no es válida, o si esta
        instalación fue revocada y la clave no cambió.
        """
        delay = 1.0
        while True:
            try:
                self.state = self._enroll.execute(self.enrollment_key, self.name)
                return self.state
            except EnrollmentError:
                raise
            except NETWORK_ERRORS as exc:
                if not retry or self._stop.is_set():
                    raise
                _log(f'API no disponible ({exc}); reintento en {delay:.0f}s')
                if self._stop.wait(delay):
                    raise
                delay = min(delay * 2, MAX_BACKOFF)

    def refresh(self) -> None:
        """Heartbeat; adopta el token nuevo cuando el actual pasó la mitad de su vida."""
        assert self.state is not None
        try:
            self._refresh.execute(self.state)
        except EnrollmentError:
            self.revoked.set()
            raise

    # ---- lo que consume el sender ------------------------------------------
    def token(self) -> str | None:
        with self._lock:
            if self.state is None or self.state.revoked:
                return None
            return self.state.access_token

    def identity(self) -> dict:
        assert self.state is not None
        return self.state.identity()

    # ---- hilo del heartbeat ------------------------------------------------
    def start(self) -> None:
        """Corre el heartbeat en un hilo daemon."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name='sensor-refresh', daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)

    def _loop(self) -> None:
        assert self.state is not None
        interval = max(self.state.refresh_interval_seconds, MIN_REFRESH_INTERVAL)
        while not self._stop.wait(interval):
            try:
                self.refresh()
            except EnrollmentError as exc:
                _log(f'sensor revocado, se detiene el envío: {exc}')
                return
            except NETWORK_ERRORS as exc:
                _log(f'no se pudo renovar el token: {exc}')
