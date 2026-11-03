"""Build idempotent analytical summaries from normalized alert Parquet data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

SUMMARY_TYPES = ("runs", "clients", "ips", "topics", "temporal")
REQUIRED_COLUMNS = {"alert_id", "ts_utc", "kind", "label"}
GROUP_COLUMNS = {
    "clients": "client_id",
    "ips": "ip",
    "topics": "topic",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _counts(values: pd.Series) -> str:
    return _json(Counter(str(value) for value in values.dropna()))


def _frequency(frame: pd.DataFrame) -> tuple[str, int, str | None]:
    windows = frame["ts"].dt.floor("min").value_counts().sort_index()
    if windows.empty:
        return "{}", 0, None
    max_count = int(windows.max())
    max_windows = [ts.isoformat() for ts, count in windows.items()
                   if count == max_count]
    return _json({ts.isoformat(): int(count) for ts, count in windows.items()}), \
        max_count, _json(max_windows)


def _source_partition(input_path: Path) -> str:
    return str(input_path)


def _period(frame: pd.DataFrame) -> tuple[str, str]:
    first = frame["ts"].min()
    last = frame["ts"].max()
    return first.isoformat(), last.isoformat()


def _base_columns(period_start: str, period_end: str, source: str) -> dict[str, str]:
    return {
        "period_start": period_start,
        "period_end": period_end,
        "source_partition": source,
    }


def _run_summary(frame: pd.DataFrame, source: str, invalid_records: int) -> pd.DataFrame:
    period_start, period_end = _period(frame)
    distributions = {
        "label": _counts(frame["label"]),
        "kind": _counts(frame["kind"]),
        "source": _counts(frame["source"]),
    }
    incomplete = frame[list({"client_id", "ip", "topic", "source"} & set(frame))].isna().any(
        axis=1).sum()
    row = _base_columns(period_start, period_end, source)
    row.update({
        "alert_count": len(frame),
        "first_alert_ts": period_start,
        "last_alert_ts": period_end,
        "observed_duration_seconds": (frame["ts"].max() - frame["ts"].min()).total_seconds(),
        "distinct_clients": int(frame["client_id"].nunique(dropna=True)),
        "distinct_ips": int(frame["ip"].nunique(dropna=True)),
        "distinct_topics": int(frame["topic"].nunique(dropna=True)),
        "label_counts": distributions["label"],
        "kind_counts": distributions["kind"],
        "source_counts": distributions["source"],
        "invalid_record_count": int(invalid_records),
        "incomplete_record_count": int(incomplete),
        "incomplete_data_percentage": float(incomplete / len(frame) * 100),
        "source_file": source,
    })
    return pd.DataFrame([row])


def _entity_summary(frame: pd.DataFrame, group: str, source: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for entity, group_frame in frame.groupby(group, dropna=True, sort=True):
        frequency, max_count, peak_windows = _frequency(group_frame)
        period_start, period_end = _period(group_frame)
        row = _base_columns(period_start, period_end, source)
        row.update({
            group[:-3] + "_id" if group.endswith("_id") else group: entity,
            "alert_count": len(group_frame),
            "first_alert_ts": period_start,
            "last_alert_ts": period_end,
            "elapsed_seconds": (group_frame["ts"].max() - group_frame["ts"].min()).total_seconds(),
            "label_counts": _counts(group_frame["label"]),
            "distinct_topics": int(group_frame["topic"].nunique(dropna=True)),
            "distinct_clients": int(group_frame["client_id"].nunique(dropna=True)),
            "frequency_by_minute": frequency,
            "max_window_alert_count": max_count,
            "peak_windows": peak_windows,
            "alert_count_by_minute": frequency,
            "source_file": source,
        })
        if group == "ip":
            row.pop("distinct_topics", None)
            row["client_count"] = row.pop("distinct_clients")
            row.pop("frequency_by_minute", None)
            row["alert_count_by_minute"] = frequency
        if group == "topic":
            row.pop("distinct_topics", None)
            row["client_count"] = row.pop("distinct_clients")
        rows.append(row)
    return pd.DataFrame(rows)


def _temporal_summary(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    ordered = frame.sort_values("ts")
    intervals = ordered["ts"].diff().dt.total_seconds().dropna()
    windows = ordered.groupby(ordered["ts"].dt.floor("min")).size()
    rows = []
    for window_start, count in windows.items():
        rows.append({
            "period_start": window_start.isoformat(),
            "period_end": (window_start + pd.Timedelta(minutes=1)).isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": (window_start + pd.Timedelta(minutes=1)).isoformat(),
            "alert_count": int(count),
            "source_partition": source,
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        result["mean_consecutive_interval_seconds"] = float(intervals.mean()) if not intervals.empty else None
        result["min_consecutive_interval_seconds"] = float(intervals.min()) if not intervals.empty else None
        result["max_consecutive_interval_seconds"] = float(intervals.max()) if not intervals.empty else None
    return result


def _atomic_parquet(frame: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp",
            delete=False) as handle:
        temporary = Path(handle.name)
    try:
        frame.to_parquet(temporary, index=False, engine="pyarrow")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_summaries(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Create all summary Parquets and update the processing checkpoint."""
    input_file = Path(input_path)
    destination = Path(output_dir)
    if not input_file.is_file():
        raise FileNotFoundError(f"Normalized Parquet does not exist: {input_file}")
    frame = pd.read_parquet(input_file, engine="pyarrow")
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Normalized Parquet is missing columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Normalized Parquet contains no alerts")

    frame = frame.drop_duplicates("alert_id").copy()
    frame["ts"] = pd.to_datetime(frame["ts_utc"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["ts"])
    if frame.empty:
        raise ValueError("Normalized Parquet contains no valid timestamps")
    for column in ("client_id", "ip", "topic", "source"):
        if column not in frame:
            frame[column] = pd.NA
    frame = frame.sort_values("ts")
    source = _source_partition(input_file)
    report_path = input_file.parent / "processing_report.json"
    invalid_records = 0
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        invalid_records = int(report.get("invalid_records", 0))

    outputs = {
        "runs": _run_summary(frame, source, invalid_records),
        "clients": _entity_summary(frame, "client_id", source),
        "ips": _entity_summary(frame, "ip", source),
        "topics": _entity_summary(frame, "topic", source),
        "temporal": _temporal_summary(frame, source),
    }
    for summary_type, summary_frame in outputs.items():
        _atomic_parquet(summary_frame, destination / summary_type / "summary.parquet")

    checkpoint = {
        "version": 1,
        "input_file": str(input_file),
        "input_sha256": _file_fingerprint(input_file),
        "input_rows": int(len(frame)),
        "output_files": [
            str(destination / summary_type / "summary.parquet")
            for summary_type in SUMMARY_TYPES
        ],
    }
    checkpoint_path = destination / "checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(checkpoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate idempotent summaries from normalized alerts.")
    parser.add_argument("--input", default="/alerts/normalized/alerts.parquet")
    parser.add_argument("--output", default="/processed/summaries")
    args = parser.parse_args()
    checkpoint = build_summaries(args.input, args.output)
    print(f"Resúmenes publicados: {len(checkpoint['output_files'])}; "
          f"alertas: {checkpoint['input_rows']}")


if __name__ == "__main__":
    main()
