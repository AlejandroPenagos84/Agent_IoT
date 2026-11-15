"""Conexión TCP + TLS (agente remoto en la central)."""

from __future__ import annotations

import socket
import ssl


class TlsConnector:
    def __init__(
        self,
        host: str,
        port: int,
        context: ssl.SSLContext,
        server_name: str | None = None,
    ):
        self.host = host
        self.port = port
        self.context = context
        self.server_name = server_name

    def open(self, timeout: float) -> socket.socket:
        raw = socket.create_connection((self.host, self.port), timeout=timeout)

        try:
            return self.context.wrap_socket(raw, server_hostname=self.server_name or self.host)
        except Exception:
            raw.close()
            raise
