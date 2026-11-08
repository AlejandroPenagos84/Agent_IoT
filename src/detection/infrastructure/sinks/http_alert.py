"""HTTPS alert sink: POST alerts to the detection API from a background thread."""

from __future__ import annotations

import json
import queue
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

from detection.application.ports.ports_out import AlertSink
from detection.domain.model import Alert

DEFAULT_QUEUE_SIZE = 10_000
DEFAULT_TIMEOUT = 10.0


class HttpAlertSink(AlertSink):
    """Deliver alerts to the Python API without blocking detection.

    ``emit`` only enqueues; a daemon thread posts JSON with a Bearer token and
    retries a few times. Failures are logged and counted; the daily JSONL sink
    remains the local fallback.
    """

    def __init__(self, url: str, token: str | Callable[[], str], timeout: float = DEFAULT_TIMEOUT,
                 tls_ca: str | None = None,
                 queue_size: int = DEFAULT_QUEUE_SIZE,
                 retries: int = 3):
        self.url = url
        self.token = token
        self.timeout = timeout
        self.retries = max(1, retries)
        self._queue: queue.Queue[Alert | None] = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self.context = None
        if url.startswith('https://'):
            self.context = (ssl.create_default_context(cafile=tls_ca)
                            if tls_ca else ssl.create_default_context())
        self._thread = threading.Thread(target=self._run, name='http-alerts',
                                        daemon=True)
        self._thread.start()

    def emit(self, alert: Alert) -> None:
        """Queue an alert for delivery; never blocks the detector."""
        if self._stop.is_set():
            self.dropped += 1
            return
        try:
            self._queue.put_nowait(alert)
        except queue.Full:
            self.dropped += 1
            print('[alerts] cola HTTP llena; alerta descartada',
                  file=sys.stderr, flush=True)

    def _token(self) -> str:
        return self.token() if callable(self.token) else self.token

    def _post(self, alert: Alert) -> bool:
        body = json.dumps(alert.to_dict(), ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(
            self.url, data=body, method='POST',
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self._token()}'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout,
                                        context=self.context) as response:
                response.read()
            return True
        except (urllib.error.HTTPError, urllib.error.URLError,
                OSError, ValueError):
            return False

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                alert = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if alert is None:
                break
            delivered = False
            for attempt in range(self.retries):
                if self._post(alert):
                    delivered = True
                    break
                if self._stop.wait(min(0.5 * (attempt + 1), 2.0)):
                    break
            with self._lock:
                if delivered:
                    self.sent += 1
                else:
                    self.failed += 1
            if not delivered:
                print(f'[alerts] no se pudo enviar {alert.alert_id} al API',
                      file=sys.stderr, flush=True)

    def close(self, timeout: float = 5.0) -> None:
        """Drain queued alerts for a while, then stop the sender thread."""
        deadline = time.monotonic() + timeout
        while not self._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.05)
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {'sent': self.sent, 'failed': self.failed,
                    'dropped': self.dropped}
