from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from typing import Callable, Iterator

from core.clock import SystemClock
from core.protocols import Clock
from core.types import ClientMeta, ConnectionEvent

RE_CONNECTION = re.compile(
    r'New connection from (?P<ip>[^:\s]+):(?P<port>\d+) on port (?P<dstport>\d+)')
RE_CONNECTED = re.compile(
    r'New client connected from (?P<ip>[^:\s]+):(?P<port>\d+) as (?P<cid>.+?) '
    r'\((?P<flags>.*?)\)\.?$')
RE_DISCONNECTED = re.compile(r'Client (?P<cid>.+?) disconnected')
RE_PUBLISH = re.compile(
    r"Received PUBLISH from (?P<cid>\S+) \(.*?'(?P<topic>[^']*)'.*?"
    r"\((?P<size>\d+) bytes\)")
RE_USERNAME = re.compile(r"u'([^']*)'")


class BrokerLogRegistry:
    def __init__(self, path: str, clock: Clock | None = None,
                 from_start: bool = False, poll: float = 0.2):
        self.path = path
        self.clock = clock or SystemClock()
        self.from_start = from_start
        self.poll = poll
        self._clients: dict[str, ClientMeta] = {}
        self._pending: dict[tuple[str, int], int] = {}
        self._owner: dict[str, str] = {}
        self._queue: deque[ConnectionEvent] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._offset = 0

    def start(self) -> None:
        if self.from_start:
            self._offset = 0
        else:
            try:
                self._offset = os.path.getsize(self.path)
            except OSError:
                self._offset = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def get(self, client_id: str) -> ClientMeta | None:
        with self._lock:
            return self._clients.get(client_id)

    def owner(self, topic: str) -> str | None:
        with self._lock:
            return self._owner.get(topic)

    def attributor(self) -> Callable[[str, bytes], str | None]:
        def resolve(topic: str, payload: bytes) -> str | None:
            return self.owner(topic)
        return resolve

    def events(self) -> Iterator[ConnectionEvent]:
        while not self._stop.is_set():
            with self._lock:
                event = self._queue.popleft() if self._queue else None
            if event is None:
                time.sleep(self.poll)
                continue
            yield event

    def _run(self) -> None:
        partial = ''
        while not self._stop.is_set():
            chunk = ''
            try:
                with open(self.path, 'r', errors='replace') as handle:
                    handle.seek(self._offset)
                    chunk = handle.read()
                    self._offset = handle.tell()
            except FileNotFoundError:
                chunk = ''
            if not chunk:
                time.sleep(self.poll)
                continue
            lines = (partial + chunk).split('\n')
            partial = lines.pop()
            for line in lines:
                self._ingest(line)

    def _ingest(self, line: str) -> None:
        match = RE_CONNECTED.search(line)
        if match:
            ip = match['ip']
            port = int(match['port'])
            cid = match['cid']
            username_match = RE_USERNAME.search(match['flags'])
            username = username_match.group(1) if username_match else None
            dstport = self._pending.pop((ip, port), 0)
            event = ConnectionEvent(ts=self._timestamp(line), client_id=cid, ip=ip,
                                    srcport=port, dstport=dstport,
                                    username=username, anonymous=username is None)
            with self._lock:
                self._clients[cid] = ClientMeta(cid, ip, port, dstport)
                self._queue.append(event)
            return

        match = RE_CONNECTION.search(line)
        if match:
            self._pending[(match['ip'], int(match['port']))] = int(match['dstport'])
            return

        match = RE_PUBLISH.search(line)
        if match:
            with self._lock:
                self._owner[match['topic']] = match['cid']
            return

    def _timestamp(self, line: str) -> float:
        head = line.split(':', 1)[0]
        try:
            return float(head)
        except ValueError:
            return self.clock.now()
