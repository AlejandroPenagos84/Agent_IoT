"""Apertura del socket de escucha del agente, según el esquema del endpoint."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Awaitable, Callable
from typing import Protocol

from wire.protocol import UNIX, parse_endpoint

from .tls_listener import TlsListener
from .unix_listener import UnixListener

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


class Listener(Protocol):
    """Abre el servidor asyncio y limpia lo que deje al cerrar."""

    port: int | None

    async def open(self, handler: Handler, limit: int, backlog: int) -> asyncio.AbstractServer: ...

    def cleanup(self) -> None: ...


def listener_for(endpoint: str, ssl_context: ssl.SSLContext | None = None) -> Listener:
    """Listener para ``unix:///ruta``, una ruta sin esquema o ``tls://host:puerto``."""
    scheme, address = parse_endpoint(endpoint)

    if scheme == UNIX:
        return UnixListener(str(address))

    host, port = address
    return TlsListener(host, port, ssl_context)
