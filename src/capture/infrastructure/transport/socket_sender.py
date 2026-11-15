"""Envío NDJSON al agente sin bloquear a tshark."""

from __future__ import annotations

import socket
import ssl
import threading
import time
from collections.abc import Callable

from capture.application.ports.record_sender import RecordSender
from capture.infrastructure.transport.connector import Connector, connector_for
from capture.infrastructure.transport.drop_oldest_queue import DropOldestQueue
from capture.infrastructure.transport.sender_stats import SenderStats
from capture.infrastructure.transport.token_auth import TokenAuth

DEFAULT_ENDPOINT = 'unix:///capture/features.sock'
DEFAULT_QUEUE_SIZE = 50_000
BATCH_SIZE = 500

# Tiempo máximo que el hilo espera datos antes de revisar token, cierre y stats.
IDLE_WAIT_SECONDS = 1.0
MIN_WAIT_SECONDS = 0.1

SEND_ERRORS = (OSError, ssl.SSLError)
HANDSHAKE_ERRORS = (OSError, ssl.SSLError, ConnectionError)


class SocketSender(RecordSender):
    """Encola registros y los envía al agente desde un hilo propio.

    ``send`` solo agrega a una cola acotada. El hilo dueño del socket conecta,
    hace el handshake, reconecta si falla o si cambia el token, y reporta
    contadores cada ``stats_seconds``.
    """

    def __init__(
        self,
        connector: Connector,
        auth: TokenAuth,
        queue: DropOldestQueue,
        stats: SenderStats,
        *,
        retry_seconds: float = 1.0,
        connect_timeout: float = 10.0,
    ):
        self._connector = connector
        self._auth = auth
        self._queue = queue
        self._stats = stats
        self._retry_seconds = max(retry_seconds, MIN_WAIT_SECONDS)
        self._connect_timeout = max(connect_timeout, MIN_WAIT_SECONDS)

        self._stop = threading.Event()
        self._closing = False
        self._deadline: float | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def from_endpoint(
        cls,
        endpoint: str = DEFAULT_ENDPOINT,
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        retry_seconds: float = 1.0,
        stats_seconds: float = 60.0,
        connect_timeout: float = 10.0,
        tls_context: ssl.SSLContext | None = None,
        server_name: str | None = None,
        sensor_token: str | None = None,
        token_provider: Callable[[], str | None] | None = None,
    ) -> SocketSender:
        """Arma el sender desde la configuración de la captura.

        ``token_provider`` (inscripción) tiene prioridad sobre ``sensor_token`` fijo.
        """
        if token_provider is not None:
            auth = TokenAuth(token_provider)
        else:
            auth = TokenAuth.static(sensor_token)

        stats = SenderStats(interval=stats_seconds)
        return cls(
            connector_for(endpoint, tls_context, server_name),
            auth,
            DropOldestQueue(queue_size, on_drop=stats.on_dropped),
            stats,
            retry_seconds=retry_seconds,
            connect_timeout=connect_timeout,
        )

    # ---- API pública -------------------------------------------------------
    def start(self) -> None:
        """Arranca el hilo de envío una sola vez."""
        if self._thread is not None:
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='feature-sender', daemon=True)
        self._thread.start()

    def send(self, line: str) -> None:
        """Encola una línea NDJSON sin bloquear."""
        if not line.endswith('\n'):
            line += '\n'

        self._queue.put(line)

    def close(self, timeout: float = 2.0) -> None:
        """Intenta vaciar la cola durante ``timeout`` segundos y luego detiene el hilo."""
        self._closing = True
        self._deadline = time.monotonic() + timeout
        self._queue.wake_all()

        if self._thread is not None:
            self._thread.join(timeout + 0.5)

        self._stop.set()
        self._queue.wake_all()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(1.0)

        # Si el hilo corrió, ya imprimió el reporte final al salir.
        if self._thread is None:
            self._stats.report()

    @property
    def stats(self) -> dict:
        """Contadores acumulados: enviados, descartados y reconexiones."""
        return self._stats.snapshot()

    # ---- hilo de envío -----------------------------------------------------
    def _run(self) -> None:
        sock: socket.socket | None = None

        while self._keep_running():
            if sock is None:
                sock = self._connect()
                if sock is None:
                    self._stop.wait(self._retry_seconds)
                    continue

            has_data = self._queue.wait(IDLE_WAIT_SECONDS)
            if not self._keep_running():
                break

            # Token renovado: el siguiente lote sale por una conexión nueva.
            if self._auth.changed():
                _close(sock)
                sock = None
                continue

            if has_data:
                batch = self._queue.take(BATCH_SIZE)
                if not self._ship(sock, batch):
                    _close(sock)
                    sock = None
                    continue

            self._stats.report_if_due()

        if sock is not None:
            _close(sock)

        self._stats.report()

    def _connect(self) -> socket.socket | None:
        """Socket listo para enviar, o ``None`` si está en pausa o falló."""
        if self._auth.paused():
            return None

        try:
            sock = self._connector.open(self._connect_timeout)
        except SEND_ERRORS:
            return None

        try:
            sock.settimeout(self._connect_timeout)
            self._auth.handshake(sock)
        except HANDSHAKE_ERRORS:
            _close(sock)
            return None

        self._stats.on_connected()
        return sock

    def _ship(self, sock: socket.socket, batch: list[str]) -> bool:
        """Envía el lote; si falla, lo cuenta como descartado."""
        if not batch:
            return True

        payload = ''.join(batch).encode('utf-8')

        try:
            sock.sendall(payload)
        except SEND_ERRORS:
            self._stats.on_dropped(len(batch))
            return False

        self._stats.on_sent(len(batch))
        return True

    def _keep_running(self) -> bool:
        if self._stop.is_set():
            return False

        if not self._closing:
            return True

        # Cerrando: sigue solo mientras quede algo y no venza el plazo.
        if len(self._queue) == 0:
            return False

        return self._deadline is not None and time.monotonic() < self._deadline


def _close(sock: socket.socket) -> None:
    try:
        sock.close()
    except OSError:
        pass
