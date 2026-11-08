"""Build a compact JSON report from analytical alert summaries."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

SUMMARY_TYPES = ("clients", "ips", "topics", "temporal")


def _read_summary(root: Path, summary_type: str) -> pd.DataFrame:
    path = root / summary_type / "summary.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"Summary Parquet does not exist: {path}")
    return pd.read_parquet(path, engine="pyarrow")


def _timestamp(value: Any) -> pd.Timestamp:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid timestamp in summary: {value!r}")
    return parsed


def _window(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if "period_start" not in frame or "period_end" not in frame:
        raise ValueError("Summary is missing period_start or period_end")
    result = frame.copy()
    result["_start"] = result["period_start"].map(_timestamp)
    result["_end"] = result["period_end"].map(_timestamp)
    return result[(result["_end"] >= start) & (result["_start"] <= end)].copy()


def _json_counts(value: Any) -> dict[str, int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON distribution: {value!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object distribution, got {parsed!r}")
    return {str(key): int(count) for key, count in parsed.items()}


def _sum_counts(values: pd.Series) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for value in values:
        counts.update(_json_counts(value))
    return dict(sorted(counts.items()))


def _meaningful_alert_types(counts: dict[str, int], total: int) -> dict[str, int] | None:
    """Hide the invariant generic attack label from the model input."""
    if counts == {"ataque": total}:
        return None
    return counts


def _union_json_arrays(frame: pd.DataFrame, column: str) -> list[str]:
    values: set[str] = set()
    if column not in frame:
        return []
    for value in frame[column].dropna():
        parsed = json.loads(value) if isinstance(value, str) else value
        if isinstance(parsed, list):
            values.update(str(item) for item in parsed)
    return sorted(values)


def _iso(value: pd.Timestamp, timezone_name: str = "UTC") -> str:
    result = value.tz_convert(ZoneInfo(timezone_name)).isoformat()
    return result.replace("+00:00", "Z") if timezone_name == "UTC" else result


def _write_text_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _entity_rows(
    frame: pd.DataFrame, entity_column: str, timezone_name: str
) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    rows = []
    for _, row in frame.sort_values("alert_count", ascending=False).head(10).iterrows():
        item: dict[str, Any] = {
            entity_column: row[entity_column],
            "alert_count": int(row["alert_count"]),
            "alert_types": _json_counts(row["label_counts"]),
            "first_alert": _iso(_timestamp(row["first_alert_ts"]), timezone_name),
            "last_alert": _iso(_timestamp(row["last_alert_ts"]), timezone_name),
        }
        if entity_column == "client_id":
            item["distinct_topics"] = int(row["distinct_topics"])
            item["peak_windows"] = json.loads(row["peak_windows"])
        elif entity_column == "ip":
            item["client_count"] = int(row["client_count"])
        else:
            item["client_count"] = int(row["client_count"])
            item["frequency_by_minute"] = json.loads(row["frequency_by_minute"])
        rows.append(item)
    return rows


def _activity_summary(
    temporal_rows: list[dict[str, Any]], timezone_name: str
) -> dict[str, Any]:
    if not temporal_rows:
        return {
            "active_window_count": 0,
            "active_minutes": 0,
            "peak_alert_count": 0,
            "peak_concentration_percentage": 0.0,
            "bursty_window_count": 0,
            "hourly_alert_count": {},
        }
    counts = [item["alert_count"] for item in temporal_rows]
    total = sum(counts)
    peak = max(counts)
    hourly: Counter[str] = Counter()
    for item in temporal_rows:
        hour = _iso(_timestamp(item["window_start"]), timezone_name)[:13] + ":00:00"
        hourly[hour] += item["alert_count"]
    burst_threshold = max(3, peak * 0.5)
    return {
        "active_window_count": len(temporal_rows),
        "active_minutes": len(temporal_rows),
        "peak_alert_count": peak,
        "peak_concentration_percentage": round(peak / total * 100, 2),
        "bursty_window_count": sum(count >= burst_threshold for count in counts),
        "hourly_alert_count": dict(sorted(hourly.items())),
    }


def build_last_24h_report(
    summaries_dir: str | Path,
    *,
    now: datetime | pd.Timestamp | None = None,
    output_timezone: str = "UTC",
) -> dict[str, Any]:
    """Return one JSON-compatible report for the preceding 24 hours.

    Summary entity counts are exact when the source summary is a 24-hour
    partition. For summaries spanning a wider period, entities are selected by
    period overlap and their stored aggregate is retained.
    """
    root = Path(summaries_dir)
    end = _timestamp(now or datetime.now(timezone.utc))
    start = end - pd.Timedelta(hours=24)
    run_path = root / "runs" / "summary.parquet"
    runs_all = _read_summary(root, "runs") if run_path.is_file() else pd.DataFrame()
    requested_start, requested_end = start, end
    if not runs_all.empty:
        available_start = min(_timestamp(value) for value in runs_all["period_start"])
        available_end = max(_timestamp(value) for value in runs_all["period_end"])
        if available_end < start or available_start > end:
            end = available_end
            start = end - pd.Timedelta(hours=24)
    frames = {
        summary_type: _window(_read_summary(root, summary_type), start, end)
        for summary_type in SUMMARY_TYPES
    }
    runs = _window(_read_summary(root, "runs"), start, end) if run_path.is_file() else pd.DataFrame()

    clients = frames["clients"]
    temporal = frames["temporal"]
    if clients.empty:
        if runs_all.empty:
            raise ValueError("No client alerts found and no run summary is available")
        if runs.empty:
            raise ValueError(
                "No alerts found in the last 24 hours "
                f"({requested_start.isoformat()} to {requested_end.isoformat()}) "
                "and no usable historical period was found. "
                f"Available summary data is {available_start.isoformat()} to "
                f"{available_end.isoformat()} UTC. "
                "Regenerate summaries from recent alerts or use a valid historical "
                "reference timestamp."
            )

    general_source = runs if not runs.empty else clients
    total_alerts = int(general_source["alert_count"].sum())
    if not temporal.empty:
        first = min(
            _timestamp(value)
            for value in temporal.get("first_alert_ts", temporal["window_start"])
        )
        last = max(
            _timestamp(value)
            for value in temporal.get("last_alert_ts", temporal["window_end"])
        )
        total_alerts = int(temporal["alert_count"].sum())
        alert_types = _sum_counts(temporal["label_counts"]) \
            if "label_counts" in temporal else _sum_counts(general_source["label_counts"])
    else:
        first = min(_timestamp(value) for value in general_source["first_alert_ts"])
        last = max(_timestamp(value) for value in general_source["last_alert_ts"])
        alert_types = _sum_counts(general_source["label_counts"])
    general = {
        "total_alerts": total_alerts,
        "clients_with_alerts": len(_union_json_arrays(temporal, "client_ids")) \
            if "client_ids" in temporal else int(len(clients)),
        "first_alert": _iso(first, output_timezone),
        "last_alert": _iso(last, output_timezone),
        "distinct_ips": len(_union_json_arrays(temporal, "ips")) \
            if "ips" in temporal else int(frames["ips"].shape[0]),
        "distinct_topics": len(_union_json_arrays(temporal, "topics")) \
            if "topics" in temporal else int(frames["topics"].shape[0]),
        "analyzed_duration_seconds": min(
            (last - first).total_seconds(), (end - start).total_seconds()
        ),
        "data_quality_notes": (
            ["No client identifiers were available in the selected period."]
            if clients.empty
            else []
        ),
    }
    meaningful_types = _meaningful_alert_types(alert_types, total_alerts)
    if meaningful_types is not None:
        general["alert_types"] = meaningful_types

    intervals: dict[str, float | None] = {
        "average_seconds": None,
        "minimum_seconds": None,
        "maximum_seconds": None,
    }
    if not temporal.empty:
        row = temporal.iloc[0]
        intervals = {
            "average_seconds": row.get("mean_consecutive_interval_seconds"),
            "minimum_seconds": row.get("min_consecutive_interval_seconds"),
            "maximum_seconds": row.get("max_consecutive_interval_seconds"),
        }
        intervals = {
            key: None if pd.isna(value) else float(value)
            for key, value in intervals.items()
        }

    temporal_rows = []
    if not temporal.empty:
        temporal_rows = [
            {
                "window_start": _iso(_timestamp(row["window_start"]), output_timezone),
                "window_end": _iso(_timestamp(row["window_end"]), output_timezone),
                "alert_count": int(row["alert_count"]),
                "first_alert": _iso(_timestamp(row.get(
                    "first_alert_ts", row["window_start"])), output_timezone),
                "last_alert": _iso(_timestamp(row.get(
                    "last_alert_ts", row["window_end"])), output_timezone),
                "alert_types": _json_counts(row.get("label_counts")),
                "distinct_clients": int(row.get("distinct_clients", 0)),
                "distinct_ips": int(row.get("distinct_ips", 0)),
                "distinct_topics": int(row.get("distinct_topics", 0)),
            }
            for _, row in temporal.sort_values(
                "alert_count", ascending=False
            ).iterrows()
        ]
    peak_count = max((item["alert_count"] for item in temporal_rows), default=0)
    return {
        "period": {
            "start": _iso(start, output_timezone),
            "end": _iso(end, output_timezone),
            "hours": 24,
            "requested_start": _iso(requested_start, output_timezone),
            "requested_end": _iso(requested_end, output_timezone),
            "historical_fallback": start != requested_start or end != requested_end,
        },
        "general": general,
        "clients": {"top_10": _entity_rows(clients, "client_id", output_timezone)},
        "ips": {"top_10": _entity_rows(frames["ips"], "ip", output_timezone)},
        "topics": {"top_10": _entity_rows(frames["topics"], "topic", output_timezone)},
        "temporal": {
            "alert_count_by_interval": temporal_rows,
            "consecutive_intervals_seconds": intervals,
            "activity_profile": _activity_summary(temporal_rows, output_timezone),
            "peak_windows": [
                item for item in temporal_rows if item["alert_count"] == peak_count
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the last-24-hour alert JSON without calling Ollama"
    )
    parser.add_argument("--input", default="/processed/summaries")
    parser.add_argument("--output", default="/processed/report.json")
    parser.add_argument(
        "--now",
        help="UTC reference timestamp in ISO-8601 format (defaults to current time)",
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("REPORT_TIMEZONE", "America/Bogota"),
        help="Timezone for timestamps written to the report (default: America/Bogota)",
    )
    args = parser.parse_args()
    report = build_last_24h_report(
        args.input, now=args.now, output_timezone=args.timezone
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(
        output,
        json.dumps(
            {
                **report,
                "report_generated_at": _iso(
                    pd.Timestamp.now(tz="UTC"), args.timezone
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )
    print(f"Reporte publicado: {output}")


if __name__ == "__main__":
    main()
