"""Handshake ``hello``/``hello_ack``: el sensor presenta su token al conectar."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from wire.protocol import HELLO, HELLO_ACK_FRAME, message_type

from .sensor_identity import SensorIdentity

TokenValidator = Callable[[str], dict]
# ¿Sigue vigente esta identidad en el registro? (sensor no borrado ni revocado).
ActiveCheck = Callable[[SensorIdentity], bool]

HELLO_TIMEOUT = 5.0


class SensorAuth:
    """Decide quién es la conexión.

    - Sin token (``required`` es ``False``, socket Unix local): no hay
      handshake y la conexión no tiene identidad.
    - Con token: la primera línea debe ser ``hello`` con un token válido y se
      responde ``hello_ack``. Cualquier fallo devuelve ``None`` (cerrar).
    - Con ``is_active``: además de la firma, el sensor debe seguir vigente en el
      registro. Si la consulta falla, se rechaza (falla cerrado).
    """

    def __init__(
        self,
        validator: TokenValidator | None = None,
        *,
        require_token: bool = False,
        hello_timeout: float = HELLO_TIMEOUT,
        is_active: ActiveCheck | None = None,
    ):
        self._validator = validator
        self._require_token = require_token
        self._hello_timeout = hello_timeout
        self._is_active = is_active

    @property
    def required(self) -> bool:
        return self._require_token

    async def authenticate(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> SensorIdentity | None:
        """Identidad del token tras responder ``hello_ack``, o ``None`` si se rechaza."""
        identity = await self._read_hello(reader)
        if identity is None or not await self.still_active(identity):
            return None

        try:
            writer.write(HELLO_ACK_FRAME)
            await writer.drain()
        except (ConnectionError, OSError):
            return None
        return identity

    async def still_active(self, identity: SensorIdentity) -> bool:
        """Consulta el registro fuera del event loop; sin ``is_active`` siempre ``True``."""
        if self._is_active is None:
            return True
        try:
            return bool(await asyncio.to_thread(self._is_active, identity))
        except Exception:
            return False

    async def _read_hello(self, reader: asyncio.StreamReader) -> SensorIdentity | None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=self._hello_timeout)
        except (TimeoutError, ConnectionError, ValueError, asyncio.CancelledError):
            return None
        if not line:
            return None

        kind, message = message_type(line)
        if kind != HELLO:
            return None

        token = message.get('token')
        if not isinstance(token, str) or self._validator is None:
            return None

        try:
            claims = self._validator(token)
        except Exception:
            return None

        try:
            return SensorIdentity.from_claims(claims)
        except (KeyError, TypeError):
            return None
