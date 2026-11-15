"""Heartbeat del sensor: renueva el token cuando ya pasó la mitad de su vida."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from capture.application.errors import EnrollmentError
from capture.application.ports.enrollment_api import EnrollmentApi
from capture.application.ports.sensor_state_store import SensorStateStore
from capture.domain.sensor_state import SensorState


class RefreshSensorToken:
    """Llama a la API con el secreto del sensor y adopta el token nuevo si toca.

    Un rechazo (``EnrollmentError``) significa que el sensor fue revocado o
    reinstalado en otro equipo: se marca y persiste ``revoked`` y se relanza.
    La llamada de red va fuera de ``lock`` para no bloquear a quien lee el token.
    """

    def __init__(
        self,
        api: EnrollmentApi,
        store: SensorStateStore,
        *,
        clock: Callable[[], float] = time.time,
        lock: threading.Lock | None = None,
    ):
        self._api = api
        self._store = store
        self._clock = clock
        self._lock = lock or threading.Lock()

    def execute(self, state: SensorState) -> bool:
        """Devuelve ``True`` si se adoptó un token nuevo."""
        try:
            body = self._api.refresh(state.sensor_secret)
        except EnrollmentError:
            with self._lock:
                state.revoked = True
                self._store.save(state)
            raise

        now = self._clock()
        with self._lock:
            if not state.token_due(now):
                return False
            state.adopt_token(body['access_token'], body['expires_in'], now)
            self._store.save(state)
        return True
