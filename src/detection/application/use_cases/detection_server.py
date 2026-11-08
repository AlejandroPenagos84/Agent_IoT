"""Run the multi-sensor transport and the per-broker detection pool."""

from __future__ import annotations

import threading


class DetectionServer:
    """Blocking server: starts the socket transport and waits until stopped."""

    def __init__(self, server, pool, closeables=()):
        self.server = server
        self.pool = pool
        self.closeables = tuple(closeables)
        self._stop = threading.Event()
        self._stopped = False

    def run(self) -> None:
        try:
            self.pool.start()
            self.server.start(self.pool.route)
            while not self._stop.wait(1.0):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._stop.set()
        self.server.stop()
        self.pool.stop()
        for closeable in self.closeables:
            close = getattr(closeable, 'close', None)
            if close is not None:
                close()
