"""Socket Unix (desarrollo: captura y agente en la misma máquina)."""

from __future__ import annotations

import asyncio
import os

SOCKET_MODE = 0o660


class UnixListener:
    port: int | None = None

    def __init__(self, path: str):
        self.path = path

    async def open(self, handler, limit: int, backlog: int) -> asyncio.AbstractServer:
        """Borra un socket viejo, crea el directorio y deja el socket en 0660."""
        self.cleanup()
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        server = await asyncio.start_unix_server(
            handler, path=self.path, limit=limit, backlog=backlog
        )
        os.chmod(self.path, SOCKET_MODE)
        return server

    def cleanup(self) -> None:
        try:
            os.unlink(self.path)
        except OSError:
            pass
