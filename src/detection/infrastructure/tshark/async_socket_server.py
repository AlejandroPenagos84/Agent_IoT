"""Asyncio Unix/TLS socket server for many concurrent capture sensors."""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import threading
import time
from typing import Awaitable, Callable

from detection.application.ports.types import Frame

from .record_parser import RecordParser
from .socket_sender import parse_endpoint

Route = Callable[[Frame], Awaitable[None]]
TokenValidator = Callable[[str], dict]

READ_LIMIT = 64 * 1024
MAX_CONNECTIONS = 10_000
START_TIMEOUT = 5.0
HELLO_TIMEOUT = 5.0
TLS_HANDSHAKE_TIMEOUT = 10.0
IDENTITY_KEYS = ('tenant_id', 'broker_id', 'sensor_id')


class AsyncSocketServer:
    """Accept many NDJSON streams and hand each frame to an async router.

    The asyncio event loop runs in a dedicated thread so the caller can keep a
    synchronous ``run``/``stop`` interface. The same code serves a Unix socket
    for development and a TLS TCP socket for production.
    """

    def __init__(self, endpoint: str, max_line_bytes: int = READ_LIMIT,
                 max_connections: int = MAX_CONNECTIONS,
                 ssl_context: ssl.SSLContext | None = None,
                 token_validator: TokenValidator | None = None,
                 require_token: bool = False,
                 hello_timeout: float = HELLO_TIMEOUT) -> None:
        self.endpoint = endpoint
        self.scheme, self.address = parse_endpoint(endpoint)
        self.max_line_bytes = max_line_bytes
        self.max_connections = max_connections
        self.ssl_context = ssl_context
        self.token_validator = token_validator
        self.require_token = require_token
        self.hello_timeout = hello_timeout
        self.port: int | None = None
        self.rejected = 0
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.AbstractServer | None = None
        self._stop_event: asyncio.Event | None = None
        self._tasks: set[asyncio.Task] = set()
        self._started = threading.Event()
        self._error: BaseException | None = None

    def start(self, route: Route) -> None:
        """Start the event loop and block until the socket is listening."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._started.clear()
        self._error = None
        self._thread = threading.Thread(target=self._thread_main, args=(route,),
                                        name='socket-asyncio', daemon=True)
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
        if self.scheme == 'unix':
            try:
                os.unlink(str(self.address))
            except OSError:
                pass

    def _request_stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()

    def _thread_main(self, route: Route) -> None:
        try:
            asyncio.run(self._serve(route))
        except BaseException as exc:  # surfaced by start() when bind fails
            self._error = exc
            self._started.set()

    async def _create_server(self, handler) -> asyncio.AbstractServer:
        backlog = min(max(self.max_connections, 100), 65535)
        if self.scheme == 'unix':
            path = str(self.address)
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            server = await asyncio.start_unix_server(
                handler, path=path, limit=self.max_line_bytes, backlog=backlog)
            os.chmod(path, 0o660)
            return server
        if self.ssl_context is None:
            raise ValueError('endpoint TLS sin contexto SSL')
        host, port = self.address  # type: ignore[misc]
        server = await asyncio.start_server(
            handler, host, port, limit=self.max_line_bytes, backlog=backlog,
            ssl=self.ssl_context, ssl_handshake_timeout=TLS_HANDSHAKE_TIMEOUT)
        sockets = server.sockets or []
        if sockets:
            self.port = sockets[0].getsockname()[1]
        return server

    async def _serve(self, route: Route) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        self._stop_event = asyncio.Event()
        server: asyncio.AbstractServer | None = None
        try:
            server = await self._create_server(
                lambda reader, writer: self._handle(reader, writer, route))
            self._server = server
            self._started.set()
            await self._stop_event.wait()
        finally:
            if server is not None:
                server.close()
                try:
                    await server.wait_closed()
                except Exception:
                    pass
            tasks = list(self._tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._server = None
            self._loop = None

    async def _read_hello(self, reader: asyncio.StreamReader) -> dict | None:
        """Read and validate the first ``hello`` frame with the sensor token."""
        try:
            line = await asyncio.wait_for(reader.readline(),
                                          timeout=self.hello_timeout)
        except (asyncio.TimeoutError, ConnectionError, ValueError,
                asyncio.CancelledError):
            return None
        if not line:
            return None
        try:
            message = json.loads(line.decode('utf-8', errors='replace'))
        except json.JSONDecodeError:
            return None
        if not isinstance(message, dict) or message.get('type') != 'hello':
            return None
        token = message.get('token')
        if not isinstance(token, str) or self.token_validator is None:
            return None
        try:
            claims = self.token_validator(token)
        except Exception:
            return None
        try:
            identity = {key: str(claims[key]) for key in IDENTITY_KEYS}
        except (KeyError, TypeError):
            return None
        expires = claims.get('exp')
        if isinstance(expires, (int, float)):
            identity['_exp'] = float(expires)
        return identity

    @staticmethod
    def _bind_identity(record: dict, identity: dict) -> bool:
        """Reject identity spoofing and fill missing ids from the token."""
        for key in IDENTITY_KEYS:
            value = record.get(key)
            if value is not None and str(value) != identity[key]:
                return False
            record[key] = identity[key]
        return True

    async def _handle(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter, route: Route) -> None:
        task = asyncio.current_task()
        assert task is not None
        if self._stop_event is not None and self._stop_event.is_set():
            await self._close(writer)
            return
        if len(self._tasks) >= self.max_connections:
            self.rejected += 1
            await self._close(writer)
            return
        self._tasks.add(task)
        parser = RecordParser()
        identity = None
        try:
            if self.require_token:
                identity = await self._read_hello(reader)
                if identity is None:
                    return
                try:
                    writer.write(b'{"type":"hello_ack"}\n')
                    await writer.drain()
                except (ConnectionError, OSError):
                    return
            expires = identity.pop('_exp', None) if identity else None
            while self._stop_event is not None and not self._stop_event.is_set():
                try:
                    if expires is None:
                        line = await reader.readline()
                    else:
                        # The sensor reconnects with a renewed token; a revoked
                        # one cannot, so the connection ends at token expiry.
                        remaining = expires - time.time()
                        if remaining <= 0:
                            break
                        line = await asyncio.wait_for(reader.readline(),
                                                      timeout=remaining)
                except asyncio.TimeoutError:
                    break
                except (asyncio.LimitOverrunError, ValueError):
                    break
                except (ConnectionError, asyncio.CancelledError):
                    break
                if not line:
                    break
                if len(line) > self.max_line_bytes:
                    continue
                try:
                    record = json.loads(line.decode('utf-8', errors='replace'))
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if identity is not None and not self._bind_identity(record,
                                                                   identity):
                    break
                context = parser.context(record)
                features = parser.features(record)
                if features is None:
                    continue
                await route(Frame(features=features, context=context,
                                  record=record))
        finally:
            self._tasks.discard(task)
            await self._close(writer)

    @staticmethod
    async def _close(writer: asyncio.StreamWriter) -> None:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
