"""Contadores del sender y su reporte periódico por stderr."""

from __future__ import annotations

import json
import sys
import threading
import time


class SenderStats:
    """Enviados, descartados por fallo de envío y reconexiones.

    Los descartes por cola llena los cuenta ``DropOldestQueue``; ``SocketSender``
    suma ambos al exponer ``stats``.
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

    def snapshot(self, extra_dropped: int = 0) -> dict:
        with self._lock:
            return {
                'sent': self.sent,
                'dropped': self.dropped + extra_dropped,
                'reconnects': self.reconnects,
            }

    def report_if_due(self, extra_dropped: int = 0) -> None:
        if self._clock() >= self._next_report:
            self.report(extra_dropped)

    def report(self, extra_dropped: int = 0) -> None:
        """Imprime lo ocurrido desde el reporte anterior."""
        current = self.snapshot(extra_dropped)
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
