from __future__ import annotations

from collections import defaultdict, deque

from core.types import ALERT_KIND_INTRUSION, Alert, ConnectionEvent


class ConnectionChurnRule:
    def __init__(self, threshold: int = 5, window: float = 10.0,
                 cooldown: float = 5.0, source: str = 'broker-log'):
        self.threshold = threshold
        self.window = window
        self.cooldown = cooldown
        self.source = source
        self._times: dict[str, deque[float]] = defaultdict(deque)
        self._last: dict[str, float] = {}

    def check(self, event: ConnectionEvent) -> Alert | None:
        times = self._times[event.client_id]
        times.append(event.ts)
        while times and (event.ts - times[0]) > self.window:
            times.popleft()
        if len(times) < self.threshold:
            return None
        last = self._last.get(event.client_id)
        if last is not None and (event.ts - last) < self.cooldown:
            return None
        self._last[event.client_id] = event.ts
        return Alert(ts=event.ts, kind=ALERT_KIND_INTRUSION, label='intrusion',
                     client_id=event.client_id, ip=event.ip, source=self.source)
