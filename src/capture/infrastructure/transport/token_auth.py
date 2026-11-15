"""Token del sensor y handshake ``hello``/``hello_ack`` con el agente."""

from __future__ import annotations

import socket
from collections.abc import Callable

from wire.protocol import HELLO_ACK, hello_frame, message_type

ACK_LIMIT_BYTES = 4096


class TokenAuth:
    """Decide con qué token se conecta el sender y cuándo debe reconectar.

    Hay dos modos:

    - estático (``TokenAuth.static``): un token fijo o ninguno (socket Unix local).
      Nunca pausa ni pide reconectar.
    - dinámico (``TokenAuth(provider)``): el token lo renueva la inscripción. Si el
      provider devuelve ``None`` (sensor revocado) el envío se pausa; si devuelve
      otro token, el sender reconecta con el nuevo.
    """

    def __init__(self, provider: Callable[[], str | None], *, dynamic: bool = True):
        self._provider = provider
        self._dynamic = dynamic
        self._token_in_use: str | None = None

    @classmethod
    def static(cls, token: str | None) -> TokenAuth:
        return cls(lambda: token, dynamic=False)

    def paused(self) -> bool:
        return self._dynamic and self._provider() is None

    def changed(self) -> bool:
        return self._dynamic and self._provider() != self._token_in_use

    def handshake(self, sock: socket.socket) -> None:
        """Envía el token y espera ``hello_ack``; lanza ``ConnectionError`` si no llega."""
        token = self._provider()

        if token:
            sock.sendall(hello_frame(token))

            if not _read_hello_ack(sock):
                raise ConnectionError('el agente no respondió hello_ack')

        self._token_in_use = token


def _read_hello_ack(sock: socket.socket, limit: int = ACK_LIMIT_BYTES) -> bool:
    """Lee la primera línea del servidor y comprueba que sea ``hello_ack``."""
    data = b''

    while b'\n' not in data and len(data) <= limit:
        chunk = sock.recv(1024)
        if not chunk:
            return False
        data += chunk

    line, _, _ = data.partition(b'\n')
    if not line:
        return False

    return message_type(line)[0] == HELLO_ACK
