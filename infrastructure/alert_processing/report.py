"""Build a compact JSON report from analytical alert summaries."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .ollama import generate_report

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


def _iso(value: pd.Timestamp) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _write_text_atomic(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _entity_rows(frame: pd.DataFrame, entity_column: str) -> list[dict[str, Any]]:
    rows = []
    for _, row in frame.sort_values("alert_count", ascending=False).head(10).iterrows():
        item: dict[str, Any] = {
            entity_column: row[entity_column],
            "alert_count": int(row["alert_count"]),
            "alert_types": _json_counts(row["label_counts"]),
            "first_alert": _iso(_timestamp(row["first_alert_ts"])),
            "last_alert": _iso(_timestamp(row["last_alert_ts"])),
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


def build_last_24h_report(
    summaries_dir: str | Path,
    *,
    now: datetime | pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Return one JSON-compatible report for the preceding 24 hours.

    Summary entity counts are exact when the source summary is a 24-hour
    partition. For summaries spanning a wider period, entities are selected by
    period overlap and their stored aggregate is retained.
    """
    root = Path(summaries_dir)
    end = _timestamp(now or datetime.now(timezone.utc))
    start = end - pd.Timedelta(hours=24)
    frames = {
        summary_type: _window(_read_summary(root, summary_type), start, end)
        for summary_type in SUMMARY_TYPES
    }
    run_path = root / "runs" / "summary.parquet"
    runs = _window(_read_summary(root, "runs"), start, end) if run_path.is_file() else pd.DataFrame()

    clients = frames["clients"]
    temporal = frames["temporal"]
    if clients.empty:
        available = _read_summary(root, "runs")
        if available.empty:
            raise ValueError("No client alerts found and no run summary is available")
        available_start = min(_timestamp(value) for value in available["period_start"])
        available_end = max(_timestamp(value) for value in available["period_end"])
        if available_end < start or available_start > end:
            raise ValueError(
                "No alerts found in the last 24 hours "
                f"({start.isoformat()} to {end.isoformat()}). "
                f"Available summary data is {available_start.isoformat()} to "
                f"{available_end.isoformat()} UTC. "
                "Use --now with a timestamp inside that period for a historical "
                "report, or regenerate summaries from recent alerts."
            )

    general_source = runs if not runs.empty else clients
    total_alerts = int(general_source["alert_count"].sum())
    first = min(_timestamp(value) for value in general_source["first_alert_ts"])
    last = max(_timestamp(value) for value in general_source["last_alert_ts"])
    alert_types = _sum_counts(general_source["label_counts"])
    general = {
        "total_alerts": total_alerts,
        "clients_with_alerts": int(len(clients)),
        "first_alert": _iso(first),
        "last_alert": _iso(last),
        "alert_types": alert_types,
        "analyzed_duration_seconds": min(
            (last - first).total_seconds(), (end - start).total_seconds()
        ),
        "data_quality_notes": (
            ["No client identifiers were available in the selected period."]
            if clients.empty
            else []
        ),
    }

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

    temporal_rows = [
        {
            "window_start": _iso(_timestamp(row["window_start"])),
            "window_end": _iso(_timestamp(row["window_end"])),
            "alert_count": int(row["alert_count"]),
        }
        for _, row in temporal.sort_values("alert_count", ascending=False).iterrows()
    ]
    peak_count = max((item["alert_count"] for item in temporal_rows), default=0)
    return {
        "period": {"start": _iso(start), "end": _iso(end), "hours": 24},
        "general": general,
        "clients": {"top_10": _entity_rows(clients, "client_id")},
        "ips": {"top_10": _entity_rows(frames["ips"], "ip")},
        "topics": {"top_10": _entity_rows(frames["topics"], "topic")},
        "temporal": {
            "alert_count_by_interval": temporal_rows,
            "consecutive_intervals_seconds": intervals,
            "peak_windows": [
                item for item in temporal_rows if item["alert_count"] == peak_count
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the last-24-hour alert JSON")
    parser.add_argument("--input", default="/processed/summaries")
    parser.add_argument("--output", default="/processed/report.json")
    parser.add_argument(
        "--now",
        help="UTC reference timestamp in ISO-8601 format (defaults to current time)",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("OLLAMA_BASE_URL"),
        help="Ollama base URL; if omitted, only the JSON report is generated",
    )
    parser.add_argument(
        "--ollama-model",
        default=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        help="Ollama model used for the natural-language report",
    )
    parser.add_argument(
        "--natural-output",
        default="/processed/report.md",
        help="Path for the natural-language report",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=1200.0,
        help="Ollama request timeout in seconds",
    )
    args = parser.parse_args()
    report = build_last_24h_report(args.input, now=args.now)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(
        output,
        json.dumps(
            {
                **report,
                "report_generated_at": _iso(pd.Timestamp.now(tz="UTC")),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )
    print(f"Reporte publicado: {output}")
    if args.ollama_url:
        natural_output = Path(args.natural_output)
        natural_output.parent.mkdir(parents=True, exist_ok=True)
        natural_output.unlink(missing_ok=True)
        natural_report = generate_report(
            report,
            base_url=args.ollama_url,
            model=args.ollama_model,
            timeout=args.ollama_timeout,
        )
        _write_text_atomic(natural_output, natural_report + "\n")
        print(f"Reporte natural publicado: {natural_output}")


if __name__ == "__main__":
    main()
