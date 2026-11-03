import tempfile
import unittest
from pathlib import Path

import pandas as pd

from infrastructure.alert_processing.summaries import build_summaries


class AlertSummaryTests(unittest.TestCase):
    def test_builds_all_aggregates_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normalized = root / "normalized"
            normalized.mkdir()
            source = normalized / "alerts.parquet"
            pd.DataFrame([
                {
                    "alert_id": "a-1", "ts_utc": "2026-11-03T20:00:01Z",
                    "kind": "class", "label": "dos", "client_id": "c-1",
                    "ip": "192.0.2.1", "topic": "a", "source": "classifier",
                },
                {
                    "alert_id": "a-2", "ts_utc": "2026-11-03T20:00:30Z",
                    "kind": "class", "label": "dos", "client_id": "c-1",
                    "ip": "192.0.2.1", "topic": "a", "source": "classifier",
                },
                {
                    "alert_id": "a-2", "ts_utc": "2026-11-03T20:00:30Z",
                    "kind": "class", "label": "dos", "client_id": "c-1",
                    "ip": "192.0.2.1", "topic": "a", "source": "classifier",
                },
            ]).to_parquet(source, index=False)
            (normalized / "processing_report.json").write_text(
                '{"invalid_records": 2}', encoding="utf-8")

            first = build_summaries(source, root / "processed" / "summaries")
            second = build_summaries(source, root / "processed" / "summaries")

            self.assertEqual(first["input_sha256"], second["input_sha256"])
            output = root / "processed" / "summaries"
            run = pd.read_parquet(output / "runs" / "summary.parquet")
            client = pd.read_parquet(output / "clients" / "summary.parquet")
            temporal = pd.read_parquet(output / "temporal" / "summary.parquet")
            self.assertEqual(run.loc[0, "alert_count"], 2)
            self.assertEqual(run.loc[0, "invalid_record_count"], 2)
            self.assertEqual(client.loc[0, "distinct_topics"], 1)
            self.assertEqual(client.loc[0, "max_window_alert_count"], 2)
            self.assertEqual(len(temporal), 1)

