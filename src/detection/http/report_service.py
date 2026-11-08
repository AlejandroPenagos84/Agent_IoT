"""Build tenant-scoped analytical reports and turn them into natural language."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from detection.infrastructure.repositories.registry_sqlite import RegistryStore
from detection.reporting.ollama import generate_report
from detection.reporting.scoped import build_scoped_report

WINDOW = timedelta(hours=24)
# SQLite ``until`` is exclusive; include alerts stamped exactly at ``now``.
_EPSILON = 1e-6


class ScopedReportService:
    """Read one tenant's alerts from the registry and build its report.

    Raises ``LookupError`` when the broker does not belong to the tenant,
    ``ValueError`` when there are no alerts, and ``RuntimeError`` when
    Ollama fails.
    """

    def __init__(
        self,
        *,
        store: RegistryStore,
        ollama_url: str,
        default_model: str,
        timeout: float,
        output_timezone: str = "UTC",
    ) -> None:
        self._store = store
        self._ollama_url = ollama_url
        self._default_model = default_model
        self._timeout = timeout
        self._timezone = output_timezone

    def _alerts(self, tenant_id: str, broker_id: str | None,
                end: datetime) -> list[dict]:
        until = end.timestamp() + _EPSILON
        alerts = self._store.list_alerts(
            tenant_id, limit=None, broker_id=broker_id,
            since=(end - WINDOW).timestamp(), until=until)
        if alerts:
            return alerts
        # Historical fallback: the 24 hours ending at the latest older alert.
        latest = self._store.list_alerts(
            tenant_id, limit=1, broker_id=broker_id, until=until)
        if not latest:
            return []
        last_ts = float(latest[0]["ts"])
        return self._store.list_alerts(
            tenant_id, limit=None, broker_id=broker_id,
            since=last_ts - WINDOW.total_seconds(), until=last_ts + _EPSILON)

    def analytical(self, tenant_id: str, *, broker_id: str | None = None,
                   now: datetime | None = None) -> dict[str, Any]:
        brokers = {broker["id"]: broker["name"]
                   for broker in self._store.list_brokers(tenant_id)}
        if broker_id is not None and broker_id not in brokers:
            raise LookupError("Broker no encontrado")
        end = now or datetime.now(timezone.utc)
        alerts = self._alerts(tenant_id, broker_id, end)
        if not alerts:
            raise ValueError("No hay alertas para este tenant o broker")
        scope = {"tenant_id": tenant_id, "broker_id": broker_id,
                 "broker_name": brokers.get(broker_id) if broker_id else None}
        return build_scoped_report(
            alerts, scope=scope, now=end, output_timezone=self._timezone,
            broker_names=brokers)

    def natural(self, analytical_report: dict[str, Any],
                model: str | None = None) -> str:
        # The internal tenant id adds nothing to the narrative.
        payload = {**analytical_report,
                   "scope": {key: value for key, value in
                             analytical_report.get("scope", {}).items()
                             if key != "tenant_id"}}
        return generate_report(
            payload,
            base_url=self._ollama_url,
            model=model or self._default_model,
            timeout=self._timeout,
            print_stream=False,
        )
