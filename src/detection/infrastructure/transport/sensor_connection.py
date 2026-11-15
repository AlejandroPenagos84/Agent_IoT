"""Una conexión de captura de punta a punta: auth, lectura NDJSON y enrutamiento."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable

from detection.application.ports.types import Frame

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


class _TokenExpired(Exception):
    pass


class SensorConnection:
    """Atiende un stream: autentica, lee líneas y manda cada ``Frame`` a ``route``.

    - Con identidad: la conexión termina al vencer el token (el sensor vuelve con
      uno renovado; uno revocado ya no puede) y ante un intento de suplantación.
    - Líneas demasiado largas, JSON inválido o que no sea un objeto se ignoran.
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

    async def serve(self) -> None:
        """Atiende hasta que el cliente cierre, falle algo o el servidor se detenga."""
        try:
            if self._auth.required:
                self._identity = await self._auth.authenticate(self._reader, self._writer)
                if self._identity is None:
                    return
            await self._read_loop()
        finally:
            await close_writer(self._writer)

    async def _read_loop(self) -> None:
        while not self._should_stop():
            try:
                line = await self._readline()
            except (_TokenExpired, *READ_ERRORS):
                return
            if not line:
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
        """Siguiente línea; con token que vence, espera como máximo hasta su vencimiento."""
        remaining = self._identity.remaining(self._clock()) if self._identity else None
        if remaining is None:
            return await self._reader.readline()
        if remaining <= 0:
            raise _TokenExpired
        return await asyncio.wait_for(self._reader.readline(), timeout=remaining)

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
