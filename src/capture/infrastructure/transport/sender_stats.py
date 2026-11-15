"""Contadores del sender y su reporte periódico por stderr."""

from __future__ import annotations

import json
import sys
import threading
import time


class SenderStats:
    """Enviados, descartados y reconexiones; único contador del sender.

    Los descartes llegan por dos caminos: la cola llena (``DropOldestQueue``
    llama a ``on_dropped``) y un lote cuyo envío falló (``SocketSender``).
    """

    def __init__(self, interval: float = 60.0, sink=sys.stderr, clock=time.monotonic):
        self._lock = threading.Lock()
        self._sink = sink
        self._clock = clock
        self._interval = interval
        self._next_report = clock() + interval
        self._had_connection = False
        self._reported = (0, 0, 0)

        self.sent = 0
        self.dropped = 0
        self.reconnects = 0

    def on_connected(self) -> None:
        """La primera conexión no cuenta como reconexión."""
        with self._lock:
            if self._had_connection:
                self.reconnects += 1
            self._had_connection = True

    def on_sent(self, count: int) -> None:
        with self._lock:
            self.sent += count

    def on_dropped(self, count: int) -> None:
        with self._lock:
            self.dropped += count

    def snapshot(self) -> dict:
        with self._lock:
            return {
                'sent': self.sent,
                'dropped': self.dropped,
                'reconnects': self.reconnects,
            }

    def report_if_due(self) -> None:
        if self._clock() >= self._next_report:
            self.report()

    def report(self) -> None:
        """Imprime lo ocurrido desde el reporte anterior."""
        current = self.snapshot()
        sent, dropped, reconnects = current['sent'], current['dropped'], current['reconnects']
        previous = self._reported

        self._reported = (sent, dropped, reconnects)
        self._next_report = self._clock() + self._interval

        payload = {
            'sent': sent - previous[0],
            'dropped': dropped - previous[1],
            'reconnects': reconnects - previous[2],
        }

        message = '[capture] socket ' + json.dumps(payload)
        if payload['dropped']:
            message += ' (registros descartados)'

        print(message, file=self._sink, flush=True)
