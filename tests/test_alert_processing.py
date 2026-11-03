import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infrastructure.alert_processing import AlertProcessingPipeline


class AlertProcessingTests(unittest.TestCase):
    def test_normalizes_valid_record_and_logs_missing_run_id(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'alerts.jsonl'
            output = Path(directory) / 'out'
            source.write_text(json.dumps({
                'ts': '2026-11-03T20:00:00-05:00',
                'kind': ' class ',
                'label': '  DoS   attack ',
                'client_id': ' sensor-1 ',
                'ip': '2001:db8::1',
                'topic': ' home/light ',
                'mse': '0.25',
                'source': 'custom-detector',
            }) + '\n', encoding='utf-8')

            with patch.object(AlertProcessingPipeline, '_write_parquet'):
                report = AlertProcessingPipeline(source, output).run()

            self.assertEqual(report.valid_records, 1)
            record = json.loads((output / 'processing_report.json').read_text())
            self.assertEqual(record['missing_fields'], {
                'alert_id': 1,
                'run_id': 1,
            })
            self.assertEqual(record['unknown_sources'], {'custom-detector': 1})
            saved = (output / 'processing_errors.jsonl').read_text()
            self.assertEqual(saved, '')

    def test_invalid_json_and_duplicate_are_retained_in_separate_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'alerts.jsonl'
            output = Path(directory) / 'out'
            record = {
                'ts': 1_800_000_000, 'kind': 'class', 'label': 'dos',
                'alert_id': 'a-1',
            }
            source.write_text(
                json.dumps(record) + '\n' + json.dumps(record) + '\n{bad\n',
                encoding='utf-8')

            with patch.object(AlertProcessingPipeline, '_write_parquet'):
                report = AlertProcessingPipeline(source, output).run()

            self.assertEqual(report.valid_records, 1)
            self.assertEqual(report.duplicate_records, 1)
            self.assertEqual(report.invalid_records, 1)
            self.assertIn('same_alert_id',
                          (output / 'duplicates.jsonl').read_text())
            self.assertIn('invalid_json',
                          (output / 'processing_errors.jsonl').read_text())
