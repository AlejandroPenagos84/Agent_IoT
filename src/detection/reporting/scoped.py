"""Build a tenant- or broker-scoped report from stored alert rows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import pandas as pd

from .report import build_report_from_summaries
from .summaries import prepare_alert_frame, summarize_frame

ALERT_COLUMNS = ("alert_id", "ts", "kind", "label", "broker_id", "sensor_id",
                 "client_id", "ip", "topic", "source")


def _alert_frame(alerts: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame([{key: alert.get(key) for key in ALERT_COLUMNS}
                          for alert in alerts], columns=list(ALERT_COLUMNS))
    if frame.empty:
        raise ValueError("No hay alertas para el alcance solicitado")
    frame["ts_utc"] = [
        datetime.fromtimestamp(float(ts), timezone.utc).isoformat()
        for ts in frame["ts"]
    ]
    return prepare_alert_frame(frame.drop(columns=["ts"]))


def _broker_breakdown(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    broker_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    selected = frame[(frame["ts"] >= start) & (frame["ts"] <= end)]
    rows = []
    for broker_id, group in selected.groupby(
            selected["broker_id"].fillna(""), sort=False):
        rows.append({
            "broker_id": broker_id or None,
            "broker_name": broker_names.get(broker_id) if broker_id else None,
            "alert_count": int(len(group)),
            "distinct_ips": int(group["ip"].nunique(dropna=True)),
            "distinct_sensors": int(group["sensor_id"].nunique(dropna=True)),
        })
    return sorted(rows, key=lambda row: row["alert_count"], reverse=True)


def build_scoped_report(
    alerts: Iterable[Mapping[str, Any]],
    *,
    scope: Mapping[str, Any],
    now: datetime | pd.Timestamp | None = None,
    output_timezone: str = "UTC",
    broker_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the 24-hour report for alerts that already belong to one scope.

    The caller filters ``alerts`` by tenant (and optionally broker). The
    result has the same shape as ``report.json`` plus ``scope`` and a
    per-broker breakdown of the selected period.
    """
    frame = _alert_frame(alerts)
    summaries = summarize_frame(frame, source="detection-db")
    report = build_report_from_summaries(
        summaries, now=now, output_timezone=output_timezone)
    start = pd.to_datetime(report["period"]["start"], utc=True)
    end = pd.to_datetime(report["period"]["end"], utc=True)
    report["scope"] = dict(scope)
    report["brokers"] = _broker_breakdown(frame, start, end, broker_names or {})
    return report
