"""TCP + TLS (producción: capturas remotas)."""

from __future__ import annotations

import asyncio
import ssl

TLS_HANDSHAKE_TIMEOUT = 10.0


class TlsListener:
    def __init__(self, host: str, port: int, context: ssl.SSLContext | None):
        self.host = host
        self.port: int | None = port
        self.context = context

    async def open(self, handler, limit: int, backlog: int) -> asyncio.AbstractServer:
        """Escucha con TLS; si se pidió el puerto 0, ``port`` queda con el asignado."""
        if self.context is None:
            raise ValueError('endpoint TLS sin contexto SSL')

        server = await asyncio.start_server(
            handler,
            self.host,
            self.port,
            limit=limit,
            backlog=backlog,
            ssl=self.context,
            ssl_handshake_timeout=TLS_HANDSHAKE_TIMEOUT,
        )
        sockets = server.sockets or []
        if sockets:
            self.port = sockets[0].getsockname()[1]
        return server

    def cleanup(self) -> None:
        pass
