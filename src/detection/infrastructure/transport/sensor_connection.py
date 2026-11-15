"""Una conexión de captura de punta a punta: auth, lectura NDJSON y enrutamiento."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

from detection.application.ports.types import Frame
from wire.protocol import IDLE_TIMEOUT_SECONDS

from .connection_limiter import SensorSlots
from .record_parser import RecordParser
from .sensor_auth import SensorAuth
from .sensor_identity import SensorIdentity

Route = Callable[[Frame], Awaitable[None]]

# Errores de lectura que terminan la conexión.
READ_ERRORS = (
    TimeoutError,
    asyncio.LimitOverrunError,
    ValueError,
    ConnectionError,
    asyncio.CancelledError,
)


# Cada cuánto se vuelve a preguntar al registro si el sensor sigue vigente.
RECHECK_SECONDS = 60.0


class _TokenExpired(Exception):
    pass


class _Revoked(Exception):
    pass


class _Idle(Exception):
    pass


class SensorConnection:
    """Atiende un stream: autentica, lee líneas y manda cada ``Frame`` a ``route``.

    - Con identidad: la conexión termina al vencer el token (el sensor vuelve con
      uno renovado; uno revocado ya no puede), ante un intento de suplantación y
      si el registro deja de darlo por vigente (se revisa cada ``recheck_seconds``).
    - ``sensor_slots`` limita cuántas conexiones abre a la vez un mismo sensor.
    - Se cierra tras ``idle_timeout`` segundos sin recibir nada (la captura manda
      ``ping`` para mantenerla viva).
    - JSON inválido o que no sea un objeto se ignora; una línea que supera el
      límite del reader cierra la conexión.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        auth: SensorAuth,
        route: Route,
        max_line_bytes: int,
        should_stop: Callable[[], bool],
        clock: Callable[[], float] = time.time,
        sensor_slots: SensorSlots | None = None,
        idle_timeout: float | None = IDLE_TIMEOUT_SECONDS,
        recheck_seconds: float = RECHECK_SECONDS,
    ):
        self._reader = reader
        self._writer = writer
        self._auth = auth
        self._route = route
        self._max_line_bytes = max_line_bytes
        self._should_stop = should_stop
        self._clock = clock
        self._parser = RecordParser()
        self._identity: SensorIdentity | None = None
        self._slots = sensor_slots
        self._slot: str | None = None
        self._idle_timeout = idle_timeout
        self._recheck_seconds = recheck_seconds
        self._idle_deadline: float | None = None
        self._next_check: float | None = None

    async def serve(self) -> None:
        """Atiende hasta que el cliente cierre, falle algo o el servidor se detenga."""
        try:
            if self._auth.required:
                self._identity = await self._auth.authenticate(self._reader, self._writer)
                if self._identity is None or not self._take_slot(self._identity):
                    return
                self._next_check = self._clock() + self._recheck_seconds
            await self._read_loop()
        finally:
            if self._slot is not None and self._slots is not None:
                self._slots.release(self._slot)
            await close_writer(self._writer)

    def _take_slot(self, identity: SensorIdentity) -> bool:
        if self._slots is None:
            return True
        if not self._slots.acquire(identity.sensor_id):
            return False
        self._slot = identity.sensor_id
        return True

    async def _read_loop(self) -> None:
        while not self._should_stop():
            try:
                line = await self._readline()
            except (_TokenExpired, _Revoked, _Idle, *READ_ERRORS):
                return
            if not line:
                return
            if not await self._recheck_if_due():
                return

            record = self._decode(line)
            if record is None:
                continue
            if self._identity is not None and not self._identity.bind(record):
                return

            # ``context`` primero: actualiza la caché de clientid/topic del stream
            # aunque este frame no traiga features.
            context = self._parser.context(record)
            features = self._parser.features(record)
            if features is None:
                continue
            await self._route(Frame(features=features, context=context, record=record))

    async def _readline(self) -> bytes:
        """Siguiente línea, sin esperar más allá del vencimiento del token, la
        inactividad permitida ni la próxima revisión del registro.

        Cancelar ``readline`` por timeout no pierde datos: el buffer del reader
        solo se consume cuando llega la línea completa.
        """
        if self._idle_timeout is not None:
            self._idle_deadline = self._clock() + self._idle_timeout
        while True:
            now = self._clock()
            limits = []
            remaining = self._identity.remaining(now) if self._identity else None
            if remaining is not None:
                if remaining <= 0:
                    raise _TokenExpired
                limits.append(remaining)
            if self._idle_deadline is not None:
                if now >= self._idle_deadline:
                    raise _Idle
                limits.append(self._idle_deadline - now)
            if self._next_check is not None:
                limits.append(max(self._next_check - now, 0.0))
            if not limits:
                return await self._reader.readline()
            try:
                return await asyncio.wait_for(self._reader.readline(), timeout=min(limits))
            except TimeoutError:
                if not await self._recheck_if_due():
                    raise _Revoked from None

    async def _recheck_if_due(self) -> bool:
        """Vuelve a consultar el registro si toca; ``False`` si el sensor ya no vale."""
        if self._identity is None or self._next_check is None:
            return True
        now = self._clock()
        if now < self._next_check:
            return True
        self._next_check = now + self._recheck_seconds
        return await self._auth.still_active(self._identity)

    def _decode(self, line: bytes) -> dict | None:
        if len(line) > self._max_line_bytes:
            return None
        try:
            record = json.loads(line.decode('utf-8', errors='replace'))
        except json.JSONDecodeError:
            return None
        return record if isinstance(record, dict) else None


async def close_writer(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
