from __future__ import annotations

from typing import Sequence

from core.protocols import IntrusionRule
from core.types import Alert, ConnectionEvent


class AnyRule:
    def __init__(self, rules: Sequence[IntrusionRule]):
        self.rules = list(rules)

    def check(self, event: ConnectionEvent) -> Alert | None:
        for rule in self.rules:
            alert = rule.check(event)
            if alert is not None:
                return alert
        return None
