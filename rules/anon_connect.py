from __future__ import annotations

from core.types import ALERT_KIND_INTRUSION, Alert, ConnectionEvent


class AnonymousConnectRule:
    def __init__(self, cooldown: float = 5.0, source: str = 'broker-log'):
        self.cooldown = cooldown
        self.source = source
        self._last: dict[str, float] = {}

    def check(self, event: ConnectionEvent) -> Alert | None:
        if not event.anonymous:
            return None
        last = self._last.get(event.client_id)
        if last is not None and (event.ts - last) < self.cooldown:
            return None
        self._last[event.client_id] = event.ts
        return Alert(ts=event.ts, kind=ALERT_KIND_INTRUSION, label='intrusion',
                     client_id=event.client_id, ip=event.ip, source=self.source)
