"""Per-broker workers: one detection pipeline per (tenant, broker)."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Callable

from detection.application.ports.ports_out import FeatureSource
from detection.application.ports.types import Frame
from detection.application.use_cases.agent import Agent

LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_WORKERS = 256
DEFAULT_QUEUE_SIZE = 10_000
DEFAULT_IDLE_SECONDS = 600.0
DEFAULT_REAP_INTERVAL = 60.0


class QueueFeatureSource(FeatureSource):
    """FeatureSource fed by another thread through a bounded queue."""

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE):
        self._queue: queue.Queue[Frame] = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)  # type: ignore[arg-type]
        except queue.Full:
            pass

    def submit(self, frame: Frame) -> bool:
        if self._stop.is_set():
            return False
        try:
            self._queue.put_nowait(frame)
            return True
        except queue.Full:
            return False

    def qsize(self) -> int:
        return self._queue.qsize()

    def rows(self):
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            yield item


class BrokerWorker:
    """One Agent and one bounded queue for a single broker."""

    def __init__(self, key: tuple[str, str], source: QueueFeatureSource,
                 agent: Agent):
        self.key = key
        self.source = source
        self.agent = agent
        self.last_activity = time.monotonic()
        self.thread = threading.Thread(target=self._run, name=f'broker-{key}',
                                       daemon=True)

    def start(self) -> None:
        self.thread.start()

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def submit(self, frame: Frame) -> bool:
        if not self.source.submit(frame):
            return False
        self.touch()
        return True

    def idle_for(self) -> float:
        return time.monotonic() - self.last_activity

    def _run(self) -> None:
        try:
            self.agent.run()
        except Exception:
            LOGGER.exception('broker worker %s failed', self.key)

    def stop(self, timeout: float = 2.0) -> None:
        self.source.stop()
        self.thread.join(timeout)


class BrokerPool:
    """Create one worker per broker and route frames to it.

    ``route`` is called from the asyncio I/O thread. It never blocks the event
    loop: when a worker queue is full it yields and retries, so only the slow
    broker's connection is backpressured.
    """

    def __init__(self, agent_factory: Callable[[FeatureSource], Agent],
                 max_workers: int = DEFAULT_MAX_WORKERS,
                 queue_size: int = DEFAULT_QUEUE_SIZE,
                 idle_seconds: float = DEFAULT_IDLE_SECONDS,
                 reap_interval: float = DEFAULT_REAP_INTERVAL):
        self.agent_factory = agent_factory
        self.max_workers = max_workers
        self.queue_size = queue_size
        self.idle_seconds = idle_seconds
        self.reap_interval = reap_interval
        self._workers: dict[tuple[str, str], BrokerWorker] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._create_lock: asyncio.Lock | None = None
        self._monitor: threading.Thread | None = None
        self.created = 0
        self.evicted = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._workers)

    def start(self) -> None:
        """Start the idle-worker monitor."""
        if self._monitor is not None and self._monitor.is_alive():
            return
        self._stop.clear()
        self._monitor = threading.Thread(target=self._monitor_loop,
                                         name='broker-reaper', daemon=True)
        self._monitor.start()

    def _get(self, key: tuple[str, str]) -> BrokerWorker | None:
        with self._lock:
            return self._workers.get(key)

    def _remove(self, key: tuple[str, str]) -> BrokerWorker | None:
        with self._lock:
            return self._workers.pop(key, None)

    async def route(self, frame: Frame) -> None:
        """Deliver one frame to its broker worker, waiting for capacity."""
        key = (frame.context.tenant_id or '', frame.context.broker_id or '')
        if self._create_lock is None:
            self._create_lock = asyncio.Lock()
        while not self._stop.is_set():
            worker = self._get(key)
            if worker is not None and not worker.thread.is_alive():
                self._remove(key)
                worker = None
            if worker is None:
                worker = await self._create_worker(key)
                if worker is None:
                    await asyncio.sleep(0.05)
                    continue
            if worker.submit(frame):
                return
            await asyncio.sleep(0.005)

    async def _create_worker(self, key: tuple[str, str]) -> BrokerWorker | None:
        assert self._create_lock is not None
        async with self._create_lock:
            worker = self._get(key)
            if worker is not None:
                return worker
            with self._lock:
                if len(self._workers) >= self.max_workers:
                    return None
            loop = asyncio.get_running_loop()
            worker = await loop.run_in_executor(None, self._build_worker, key)
            if self._stop.is_set():
                return None
            with self._lock:
                self._workers[key] = worker
            self.created += 1
            worker.start()
            return worker

    def _build_worker(self, key: tuple[str, str]) -> BrokerWorker:
        source = QueueFeatureSource(self.queue_size)
        agent = self.agent_factory(source)
        return BrokerWorker(key, source, agent)

    def _reap_idle(self) -> None:
        now = time.monotonic()
        with self._lock:
            idle = [(key, worker) for key, worker in self._workers.items()
                    if now - worker.last_activity >= self.idle_seconds
                    and worker.source.qsize() == 0]
            for key, _ in idle:
                self._workers.pop(key, None)
        for _, worker in idle:
            worker.stop()
            self.evicted += 1

    def _monitor_loop(self) -> None:
        while not self._stop.wait(self.reap_interval):
            self._reap_idle()

    def stop(self) -> None:
        self._stop.set()
        if self._monitor is not None:
            self._monitor.join(self.reap_interval + 1.0)
            self._monitor = None
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.source.stop()
        for worker in workers:
            worker.thread.join(2.0)
