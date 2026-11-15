"""Servidor asyncio (Unix o TLS) para muchos sensores de captura a la vez."""

from __future__ import annotations

import asyncio
import ssl
import threading

from wire.protocol import IDLE_TIMEOUT_SECONDS

from .connection_limiter import ConnectionLimiter, SensorSlots
from .listener import Listener, listener_for
from .sensor_auth import HELLO_TIMEOUT, ActiveCheck, SensorAuth, TokenValidator
from .sensor_connection import RECHECK_SECONDS, Route, SensorConnection, close_writer

READ_LIMIT = 64 * 1024
MAX_CONNECTIONS = 10_000
# Una captura usa una conexión; el margen cubre reconexiones mientras el agente
# todavía no detecta que la anterior murió.
MAX_CONNECTIONS_PER_SENSOR = 4
START_TIMEOUT = 5.0
MIN_BACKLOG = 100
MAX_BACKLOG = 65535


class AsyncSocketServer:
    """Acepta streams NDJSON y entrega cada frame a un router asíncrono.

    El event loop corre en un hilo propio para que quien lo usa tenga una
    interfaz síncrona ``start``/``stop``. Las piezas:

    - ``Listener`` abre el socket Unix o TLS (``listener_for``).
    - ``ConnectionLimiter`` aplica el tope de conexiones y las cancela al cerrar.
    - ``SensorSlots`` aplica el tope de conexiones por sensor.
    - ``SensorAuth`` hace el handshake ``hello``/``hello_ack`` con el token y,
      con ``sensor_active``, comprueba que el sensor siga vigente en el registro.
    - ``SensorConnection`` atiende cada conexión: lectura, identidad y ``route``.
    """

    def __init__(
        self,
        endpoint: str,
        max_line_bytes: int = READ_LIMIT,
        max_connections: int = MAX_CONNECTIONS,
        ssl_context: ssl.SSLContext | None = None,
        token_validator: TokenValidator | None = None,
        require_token: bool = False,
        hello_timeout: float = HELLO_TIMEOUT,
        sensor_active: ActiveCheck | None = None,
        max_connections_per_sensor: int = MAX_CONNECTIONS_PER_SENSOR,
        idle_timeout: float | None = IDLE_TIMEOUT_SECONDS,
        recheck_seconds: float = RECHECK_SECONDS,
    ) -> None:
        self.endpoint = endpoint
        self.max_line_bytes = max_line_bytes
        self._listener: Listener = listener_for(endpoint, ssl_context)
        self._limiter = ConnectionLimiter(max_connections)
        self._slots = SensorSlots(max_connections_per_sensor)
        self._auth = SensorAuth(
            token_validator,
            require_token=require_token,
            hello_timeout=hello_timeout,
            is_active=sensor_active,
        )
        self._idle_timeout = idle_timeout
        self._recheck_seconds = recheck_seconds

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._started = threading.Event()
        self._error: BaseException | None = None

    # ---- API pública -------------------------------------------------------
    @property
    def port(self) -> int | None:
        """Puerto TLS real (útil con ``tls://host:0``); ``None`` en Unix."""
        return self._listener.port

    @property
    def rejected(self) -> int:
        """Conexiones rechazadas por superar ``max_connections``."""
        return self._limiter.rejected

    @property
    def rejected_per_sensor(self) -> int:
        """Conexiones rechazadas por superar el tope de un mismo sensor."""
        return self._slots.rejected

    def start(self, route: Route) -> None:
        """Arranca el event loop y bloquea hasta que el socket está escuchando."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._started.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._thread_main, args=(route,), name='socket-asyncio', daemon=True
        )
        self._thread.start()
        if not self._started.wait(START_TIMEOUT):
            raise TimeoutError('el servidor de socket no arrancó')
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._request_stop)
        if self._thread is not None:
            self._thread.join(START_TIMEOUT)
            self._thread = None
        self._listener.cleanup()

    # ---- event loop --------------------------------------------------------
    def _request_stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    def _stopping(self) -> bool:
        return self._stop_event is None or self._stop_event.is_set()

    def _thread_main(self, route: Route) -> None:
        try:
            asyncio.run(self._serve(route))
        except BaseException as exc:  # start() lo relanza si falla el bind
            self._error = exc
            self._started.set()

    async def _serve(self, route: Route) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        server: asyncio.AbstractServer | None = None
        try:
            server = await self._listener.open(
                lambda reader, writer: self._accept(reader, writer, route),
                limit=self.max_line_bytes,
                backlog=min(max(self._limiter.max_connections, MIN_BACKLOG), MAX_BACKLOG),
            )
            self._started.set()
            await self._stop_event.wait()
        finally:
            if server is not None:
                server.close()
                try:
                    await server.wait_closed()
                except Exception:
                    pass
            await self._limiter.cancel_all()
            self._loop = None

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, route: Route
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        if self._stopping() or not self._limiter.admit(task):
            await close_writer(writer)
            return
        try:
            await SensorConnection(
                reader,
                writer,
                auth=self._auth,
                route=route,
                max_line_bytes=self.max_line_bytes,
                should_stop=self._stopping,
                sensor_slots=self._slots,
                idle_timeout=self._idle_timeout,
                recheck_seconds=self._recheck_seconds,
            ).serve()
        finally:
            self._limiter.release(task)
