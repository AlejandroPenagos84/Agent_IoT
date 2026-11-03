import json
import tempfile
import unittest
from pathlib import Path

from domain.model import Alert
from infrastructure.sinks import CompositeAlertSink, DailyFileAlertSink


class RecordingSink:
    def __init__(self):
        self.alerts = []

    def emit(self, alert):
        self.alerts.append(alert)


class AlertSinkTests(unittest.TestCase):
    def test_daily_sink_writes_one_file_per_utc_day(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = DailyFileAlertSink(directory)
            first = Alert(ts=1_800_000_000, kind='class', label='dos')
            second = Alert(ts=1_800_086_400, kind='class', label='intrusion')

            sink.emit(first)
            sink.emit(second)

            files = sorted(Path(directory).glob('*.jsonl'))
            self.assertEqual(len(files), 2)
            records = [json.loads(path.read_text(encoding='utf-8').strip())
                       for path in files]
            self.assertEqual({record['label'] for record in records},
                             {'dos', 'intrusion'})

    def test_composite_delivers_to_mqtt_and_file_sinks(self):
        mqtt = RecordingSink()
        with tempfile.TemporaryDirectory() as directory:
            file_sink = DailyFileAlertSink(directory)
            sink = CompositeAlertSink((mqtt, file_sink))
            alert = Alert(ts=1_800_000_000, kind='class', label='dos')

            sink.emit(alert)

            self.assertEqual(mqtt.alerts, [alert])
            path = next(Path(directory).glob('*.jsonl'))
            self.assertEqual(json.loads(path.read_text())['label'], 'dos')