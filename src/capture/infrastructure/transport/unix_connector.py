"""Conexión por socket Unix (agente en la misma máquina)."""

from __future__ import annotations

import socket


class UnixConnector:
    def __init__(self, path: str):
        self.path = path

    def open(self, timeout: float) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect(self.path)
        except OSError:
            sock.close()
            raise

        return sock
