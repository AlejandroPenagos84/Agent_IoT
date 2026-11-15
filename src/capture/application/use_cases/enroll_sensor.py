"""Inscribir el sensor, o reutilizar la identidad guardada si la clave no cambió."""

from __future__ import annotations

import time
from collections.abc import Callable

from capture.application.errors import EnrollmentError
from capture.application.ports.enrollment_api import EnrollmentApi
from capture.application.ports.sensor_state_store import SensorStateStore
from capture.application.use_cases.refresh_sensor_token import RefreshSensorToken
from capture.domain.sensor_state import SensorState, key_digest

REVOKED_MESSAGE = (
    'el sensor fue revocado o reinstalado en otro equipo; genera una clave nueva en la web'
)
MAX_NAME_LENGTH = 128


class EnrollSensor:
    """Un intento, sin reintentos de red (eso lo decide quien lo invoca).

    - Hay estado guardado con la misma clave: se reutiliza y se valida con un
      refresh. Si estaba revocado, o el refresh es rechazado, no se re-inscribe
      con esa clave (echaría a la otra instalación): ``EnrollmentError``.
    - No hay estado, o la clave es otra: ``POST /sensors/enroll``.
    """

    def __init__(
        self,
        api: EnrollmentApi,
        store: SensorStateStore,
        refresh: RefreshSensorToken,
        *,
        clock: Callable[[], float] = time.time,
        log: Callable[[str], None] = lambda _message: None,
    ):
        self._api = api
        self._store = store
        self._refresh = refresh
        self._clock = clock
        self._log = log

    def execute(self, enrollment_key: str, name: str) -> SensorState:
        state = self._store.load()
        if state is not None and state.enrolled_with(enrollment_key):
            return self._reuse(state)
        return self._enroll(enrollment_key, name)

    def _reuse(self, state: SensorState) -> SensorState:
        if state.revoked:
            raise EnrollmentError(REVOKED_MESSAGE)
        try:
            self._refresh.execute(state)
        except EnrollmentError:
            raise EnrollmentError(REVOKED_MESSAGE) from None
        return state

    def _enroll(self, enrollment_key: str, name: str) -> SensorState:
        body = self._api.enroll(enrollment_key, name[:MAX_NAME_LENGTH])
        now = self._clock()
        state = SensorState(
            tenant_id=body['tenant_id'],
            broker_id=body['broker_id'],
            sensor_id=body['sensor_id'],
            sensor_secret=body['sensor_secret'],
            agent_endpoint=body['agent_endpoint'],
            agent_server_name=body.get('agent_server_name') or '',
            refresh_interval_seconds=int(body.get('refresh_interval_seconds', 60)),
            enrollment_key_sha256=key_digest(enrollment_key),
        )
        state.adopt_token(body['access_token'], body['expires_in'], now)
        self._store.save_ca(body.get('agent_ca'))
        self._store.save(state)
        self._log(f'inscrito: broker={state.broker_id} sensor={state.sensor_id}')
        return state
