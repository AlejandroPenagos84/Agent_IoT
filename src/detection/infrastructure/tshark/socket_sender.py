"""Non-blocking NDJSON sender over a Unix or TLS stream socket."""

from __future__ import annotations

import json
import socket
import ssl
import sys
import threading
import time
from collections import deque
from typing import Callable

DEFAULT_ENDPOINT = 'unix:///capture/features.sock'
BATCH_SIZE = 500


def parse_endpoint(endpoint: str) -> tuple[str, object]:
    """Return ``('unix', path)`` or ``('tls', (host, port))``."""
    if '://' not in endpoint:
        return 'unix', endpoint
    scheme, rest = endpoint.split('://', 1)
    if scheme == 'unix':
        return 'unix', rest
    if scheme == 'tls':
        host, sep, port = rest.rpartition(':')
        if not sep or not host:
            raise ValueError(f'endpoint TLS inválido: {endpoint}')
        return 'tls', (host.strip('[]'), int(port))
    raise ValueError(f'esquema de endpoint no soportado: {scheme}')


class SocketSender:
    """Queue records and ship them to the agent without blocking tshark.

    ``send`` only appends to a bounded queue. A daemon thread owns the socket,
    reconnects on failure and reports counters periodically. When the queue is
    full the oldest record is dropped, which matches the best-effort nature of
    a real-time IDS.
    """

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT,
                 queue_size: int = 50_000, retry_seconds: float = 1.0,
                 stats_seconds: float = 60.0,
                 tls_context: ssl.SSLContext | None = None,
                 server_name: str | None = None,
                 sensor_token: str | None = None,
                 connect_timeout: float = 10.0,
                 token_provider: Callable[[], str | None] | None = None):
        self.endpoint = endpoint
        self.scheme, self.address = parse_endpoint(endpoint)
        self.path = self.address if self.scheme == 'unix' else None
        self.queue_size = queue_size
        self.retry_seconds = retry_seconds
        self.stats_seconds = stats_seconds
        self.tls_context = tls_context
        self.server_name = server_name
        self.sensor_token = sensor_token
        # Renewed tokens: reconnect with the new one; ``None`` pauses sending.
        self.token_provider = token_provider
        self._connected_token: str | None = None
        self.connect_timeout = connect_timeout
        self._queue: deque[str] = deque(maxlen=queue_size)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._closing = False
        self._deadline: float | None = None
        self._thread: threading.Thread | None = None
        self.sent = 0
        self.dropped = 0
        self.reconnects = 0
        self._reported = (0, 0, 0)
        self._had_connection = False

    def start(self) -> None:
        """Start the daemon sender thread once."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='feature-sender',
                                        daemon=True)
        self._thread.start()

    def send(self, line: str) -> None:
        """Queue one NDJSON line without blocking; drop the oldest if full."""
        if not line.endswith('\n'):
            line += '\n'
        with self._condition:
            if len(self._queue) == self.queue_size:
                self.dropped += 1
            self._queue.append(line)
            self._condition.notify()

    def close(self, timeout: float = 2.0) -> None:
        """Try to drain the queue for ``timeout`` seconds, then stop."""
        with self._condition:
            self._closing = True
            self._deadline = time.monotonic() + timeout
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout + 0.5)
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(1.0)
        self._report()

    @property
    def stats(self) -> dict:
        """Return cumulative counters (sent, dropped, reconnects)."""
        with self._lock:
            return {'sent': self.sent, 'dropped': self.dropped,
                    'reconnects': self.reconnects}

    def _report(self) -> None:
        with self._lock:
            sent, dropped, reconnects = self.sent, self.dropped, self.reconnects
        previous = self._reported
        self._reported = (sent, dropped, reconnects)
        payload = {
            'sent': sent - previous[0],
            'dropped': dropped - previous[1],
            'reconnects': reconnects - previous[2],
        }
        message = '[capture] socket ' + json.dumps(payload)
        if payload['dropped']:
            message += ' (registros descartados)'
        print(message, file=sys.stderr, flush=True)

    def _connect(self) -> socket.socket | None:
        timeout = max(self.connect_timeout, 0.1)
        sock: socket.socket | None = None
        try:
            if self.scheme == 'unix':
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect(str(self.address))
            else:
                host, port = self.address  # type: ignore[misc]
                sock = socket.create_connection((host, port), timeout=timeout)
                if self.tls_context is None:
                    raise ValueError('endpoint TLS sin contexto SSL')
                sock = self.tls_context.wrap_socket(
                    sock, server_hostname=self.server_name or host)
        except (FileNotFoundError, ConnectionRefusedError, OSError,
                ssl.SSLError, ValueError):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            return None
        sock.settimeout(max(self.connect_timeout, 0.1))
        token = self._current_token()
        self._connected_token = token
        if token:
            hello = json.dumps({'type': 'hello', 'token': token})
            try:
                sock.sendall((hello + '\n').encode('utf-8'))
                if not self._read_hello_ack(sock):
                    sock.close()
                    return None
            except (OSError, ssl.SSLError, socket.timeout):
                try:
                    sock.close()
                except OSError:
                    pass
                return None
        with self._lock:
            if self._had_connection:
                self.reconnects += 1
            self._had_connection = True
        return sock

    def _current_token(self) -> str | None:
        if self.token_provider is not None:
            return self.token_provider()
        return self.sensor_token

    def _token_paused(self) -> bool:
        return self.token_provider is not None and self._current_token() is None

    def _token_changed(self) -> bool:
        return (self.token_provider is not None
                and self._current_token() != self._connected_token)

    @staticmethod
    def _read_hello_ack(sock: socket.socket, limit: int = 4096) -> bool:
        """Wait for the server's ``hello_ack`` after the sensor token."""
        data = b''
        while b'\n' not in data and len(data) <= limit:
            chunk = sock.recv(1024)
            if not chunk:
                return False
            data += chunk
        line, _, _ = data.partition(b'\n')
        if not line:
            return False
        try:
            message = json.loads(line.decode('utf-8', errors='replace'))
        except json.JSONDecodeError:
            return False
        return isinstance(message, dict) and message.get('type') == 'hello_ack'

    def _take_batch(self) -> list[str]:
        with self._lock:
            count = min(BATCH_SIZE, len(self._queue))
            return [self._queue.popleft() for _ in range(count)]

    def _keep_running(self) -> bool:
        if self._stop.is_set():
            return False
        if not self._closing:
            return True
        with self._lock:
            empty = not self._queue
        if empty:
            return False
        return self._deadline is not None and time.monotonic() < self._deadline

    def _run(self) -> None:
        sock: socket.socket | None = None
        next_report = time.monotonic() + self.stats_seconds
        while self._keep_running():
            if sock is None:
                if self._token_paused():
                    self._stop.wait(max(self.retry_seconds, 0.1))
                    continue
                sock = self._connect()
                if sock is None:
                    self._stop.wait(max(self.retry_seconds, 0.1))
                    continue
            with self._condition:
                if not self._queue and not self._closing:
                    self._condition.wait(timeout=min(self.stats_seconds, 1.0))
            if not self._keep_running():
                break
            if self._token_changed():
                # Renewed token: send the next batch on a fresh connection.
                try:
                    sock.close()
                except OSError:
                    pass
                sock = None
                continue
            batch = self._take_batch()
            if not batch:
                if time.monotonic() >= next_report:
                    self._report()
                    next_report = time.monotonic() + self.stats_seconds
                continue
            payload = ''.join(batch).encode('utf-8')
            try:
                sock.sendall(payload)
            except (BrokenPipeError, ConnectionResetError, OSError,
                    ssl.SSLError, socket.timeout):
                with self._lock:
                    self.dropped += len(batch)
                try:
                    sock.close()
                except OSError:
                    pass
                sock = None
                continue
            with self._lock:
                self.sent += len(batch)
            if time.monotonic() >= next_report:
                self._report()
                next_report = time.monotonic() + self.stats_seconds
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._report()
