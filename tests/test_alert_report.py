import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from detection.reporting.report import build_last_24h_report


class AlertReportTests(unittest.TestCase):
    def test_uses_latest_available_period_when_data_is_historical(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for summary_type in ("clients", "ips", "topics", "temporal", "runs"):
                (root / summary_type).mkdir()
            period = {
                "period_start": "2026-11-03T20:00:00Z",
                "period_end": "2026-11-03T20:01:00Z",
            }
            pd.DataFrame([{
                **period,
                "alert_count": 1,
                "first_alert_ts": period["period_start"],
                "last_alert_ts": period["period_end"],
                "label_counts": '{"dos": 1}',
            }]).to_parquet(root / "runs" / "summary.parquet")
            for summary_type in ("clients", "ips", "topics", "temporal"):
                pd.DataFrame(columns=period).to_parquet(
                    root / summary_type / "summary.parquet"
                )

            report = build_last_24h_report(root, now="2026-11-05T20:01:00Z")

            self.assertTrue(report["period"]["historical_fallback"])
            self.assertEqual(report["general"]["total_alerts"], 1)

    def test_builds_last_24_hour_json_from_all_summary_perspectives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for summary_type in ("clients", "ips", "topics", "temporal"):
                (root / summary_type).mkdir()

            start = "2026-11-03T12:00:00Z"
            end = "2026-11-04T12:00:00Z"
            common = {"period_start": start, "period_end": end}
            pd.DataFrame([
                {
                    **common, "client_id": "c-1", "alert_count": 3,
                    "label_counts": json.dumps({"dos": 2, "mitm": 1}),
                    "first_alert_ts": start, "last_alert_ts": end,
                    "distinct_topics": 2, "peak_windows": "[]",
                },
            ]).to_parquet(root / "clients" / "summary.parquet")
            pd.DataFrame([
                {
                    **common, "ip": "192.0.2.1", "alert_count": 3,
                    "label_counts": '{"dos": 2, "mitm": 1}',
                    "first_alert_ts": start, "last_alert_ts": end,
                    "client_count": 1,
                },
            ]).to_parquet(root / "ips" / "summary.parquet")
            pd.DataFrame([
                {
                    **common, "topic": "devices/a", "alert_count": 3,
                    "label_counts": '{"dos": 2, "mitm": 1}',
                    "first_alert_ts": start, "last_alert_ts": end,
                    "client_count": 1, "frequency_by_minute": "{}",
                },
            ]).to_parquet(root / "topics" / "summary.parquet")
            pd.DataFrame([
                {
                    **common, "window_start": "2026-11-04T11:00:00Z",
                    "window_end": "2026-11-04T11:01:00Z", "alert_count": 3,
                    "mean_consecutive_interval_seconds": 10.0,
                    "min_consecutive_interval_seconds": 5.0,
                    "max_consecutive_interval_seconds": 15.0,
                },
            ]).to_parquet(root / "temporal" / "summary.parquet")

            report = build_last_24h_report(
                root, now=datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
            )

            self.assertEqual(report["general"]["total_alerts"], 3)
            self.assertEqual(report["general"]["alert_types"], {"dos": 2, "mitm": 1})
            self.assertEqual(report["clients"]["top_10"][0]["client_id"], "c-1")
            self.assertEqual(report["temporal"]["peak_windows"][0]["alert_count"], 3)

    def test_reference_timestamp_can_include_a_past_partition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for summary_type in ("clients", "ips", "topics", "temporal"):
                (root / summary_type).mkdir()
            period = {
                "period_start": "2026-11-03T20:00:00Z",
                "period_end": "2026-11-03T20:01:00Z",
            }
            pd.DataFrame([{
                **period, "client_id": "c-1", "alert_count": 1,
                "label_counts": '{"dos": 1}', "first_alert_ts": period["period_start"],
                "last_alert_ts": period["period_end"], "distinct_topics": 1,
                "peak_windows": "[]",
            }]).to_parquet(root / "clients" / "summary.parquet")
            pd.DataFrame([{
                **period, "ip": "192.0.2.1", "alert_count": 1,
                "label_counts": '{"dos": 1}', "first_alert_ts": period["period_start"],
                "last_alert_ts": period["period_end"], "client_count": 1,
            }]).to_parquet(root / "ips" / "summary.parquet")
            pd.DataFrame([{
                **period, "topic": "a", "alert_count": 1,
                "label_counts": '{"dos": 1}', "first_alert_ts": period["period_start"],
                "last_alert_ts": period["period_end"], "client_count": 1,
                "frequency_by_minute": "{}",
            }]).to_parquet(root / "topics" / "summary.parquet")
            pd.DataFrame(columns=[
                *period, "window_start", "window_end", "alert_count",
                "mean_consecutive_interval_seconds",
                "min_consecutive_interval_seconds",
                "max_consecutive_interval_seconds",
            ]).to_parquet(root / "temporal" / "summary.parquet")

            report = build_last_24h_report(root, now="2026-11-04T20:01:00Z")

            self.assertEqual(report["general"]["total_alerts"], 1)

    def test_ignores_invariant_generic_attack_label(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for summary_type in ("clients", "ips", "topics", "temporal", "runs"):
                (root / summary_type).mkdir()
            period = {
                "period_start": "2026-11-07T05:00:00Z",
                "period_end": "2026-11-07T05:01:00Z",
            }
            pd.DataFrame([{
                **period, "alert_count": 2, "first_alert_ts": period["period_start"],
                "last_alert_ts": period["period_end"],
                "label_counts": '{"ataque": 2}',
            }]).to_parquet(root / "runs" / "summary.parquet")
            for summary_type in ("clients", "ips", "topics"):
                pd.DataFrame(columns=period).to_parquet(
                    root / summary_type / "summary.parquet")
            pd.DataFrame([{
                **period, "window_start": period["period_start"],
                "window_end": period["period_end"], "alert_count": 2,
                "first_alert_ts": "2026-11-07T05:00:01Z",
                "last_alert_ts": "2026-11-07T05:00:02Z",
                "label_counts": '{"ataque": 2}',
            }]).to_parquet(root / "temporal" / "summary.parquet")

            report = build_last_24h_report(
                root, now="2026-11-07T05:01:00Z")

            self.assertNotIn("alert_types", report["general"])
            self.assertEqual(
                report["general"]["first_alert"], "2026-11-07T05:00:01Z")
