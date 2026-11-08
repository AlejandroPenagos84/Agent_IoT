import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from detection.application.ports.ports_out import (AlertSink, Classifier,
                                                   EvidenceSink, FeatureSource)
from detection.application.ports.types import Frame
from detection.application.use_cases.agent import Agent
from detection.domain.model import Alert, FrameContext
from detection.infrastructure.sinks.file_evidence import FileEvidenceSink


class Source(FeatureSource):
    def __init__(self, frames):
        self.frames = frames

    def start(self):
        pass

    def rows(self):
        yield from self.frames


class AlwaysAttack(Classifier):
    def predict(self, window):
        return ['ataque'] * len(window)


class AlertRecorder(AlertSink):
    def __init__(self):
        self.alerts = []

    def emit(self, alert):
        self.alerts.append(alert)


class EvidenceRecorder(EvidenceSink):
    def __init__(self):
        self.writes = []

    def write(self, alert, key, records):
        self.writes.append((alert, key, list(records)))


def frame(ts, record, reverse=False, stream=1):
    if reverse:
        src, dst, sport, dport = '10.0.0.2', '10.0.0.1', 1883, 40000
    else:
        src, dst, sport, dport = '10.0.0.1', '10.0.0.2', 40000, 1883
    return Frame({'marker': ts}, FrameContext(
        ts=ts, ip=src, dst_ip=dst, srcport=sport, dstport=dport,
        stream_id=stream, client_id='sensor1', tenant_id='tenant-1',
        broker_id='broker-1', sensor_id='sensor-1'), record)


class EvidenceAgentTests(unittest.TestCase):
    def run_agent(self, frames, **kwargs):
        alerts, evidence = AlertRecorder(), EvidenceRecorder()
        Agent(Source(frames), AlwaysAttack(), alerts, window_size=1,
              evidence_sink=evidence, **kwargs).run()
        return alerts, evidence

    def test_evidence_has_both_directions_of_the_stream(self):
        forward = {'frame.time_epoch': 0.0, 'tcp.stream': 1, 'marker': 'forward'}
        reverse = {'frame.time_epoch': 1.0, 'tcp.stream': 1, 'marker': 'reverse'}
        alerts, evidence = self.run_agent([
            frame(0.0, forward), frame(1.0, reverse, reverse=True)])
        self.assertEqual(len(alerts.alerts), 2)
        last_records = evidence.writes[-1][2]
        self.assertEqual([record['marker'] for record in last_records],
                         ['forward', 'reverse'])
        self.assertTrue(all(alert.alert_id for alert in alerts.alerts))
        self.assertEqual(alerts.alerts[0].tenant_id, 'tenant-1')
        self.assertEqual(alerts.alerts[0].broker_id, 'broker-1')
        self.assertEqual(alerts.alerts[0].sensor_id, 'sensor-1')

    def test_evidence_does_not_mix_other_streams(self):
        first = {'frame.time_epoch': 0.0, 'tcp.stream': 1, 'marker': 'one'}
        other = {'frame.time_epoch': 1.0, 'tcp.stream': 2, 'marker': 'two'}
        _, evidence = self.run_agent([frame(0.0, first),
                                      frame(1.0, other, stream=2)])
        for _, _, records in evidence.writes:
            markers = {record['marker'] for record in records}
            self.assertFalse({'one', 'two'} <= markers)

    def test_cooldown_creates_one_evidence_per_alert(self):
        record = {'frame.time_epoch': 0.0, 'tcp.stream': 1}
        alerts, evidence = self.run_agent(
            [frame(0.0, record), frame(1.0, record)], alert_cooldown=5.0)
        self.assertEqual(len(alerts.alerts), 1)
        self.assertEqual(len(evidence.writes), 1)

    def test_evidence_keeps_only_the_window(self):
        old = {'frame.time_epoch': 0.0, 'tcp.stream': 1, 'marker': 'old'}
        recent = {'frame.time_epoch': 100.0, 'tcp.stream': 1, 'marker': 'recent'}
        _, evidence = self.run_agent(
            [frame(0.0, old), frame(100.0, recent)], evidence_seconds=30.0)
        self.assertEqual([record['marker'] for record in evidence.writes[-1][2]],
                         ['recent'])


class FileEvidenceSinkTests(unittest.TestCase):
    def test_writes_alert_header_and_records_by_utc_date(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = FileEvidenceSink(directory)
            alert = Alert(ts=1_800_000_000, kind='class', label='dos',
                          alert_id='alert-1')
            sink.write(alert, ('key',), [{'frame.time_epoch': 1.0}])
            day = datetime.now(timezone.utc).date().isoformat()
            path = Path(directory) / day / 'alert-1.jsonl'
            lines = path.read_text(encoding='utf-8').splitlines()
        header = json.loads(lines[0])
        self.assertEqual(header['alert']['alert_id'], 'alert-1')
        self.assertEqual(header['alert']['ts'], 1_800_000_000)
        self.assertEqual(json.loads(lines[1])['frame.time_epoch'], 1.0)

    def test_size_cap_skips_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            sink = FileEvidenceSink(directory, max_bytes=0)
            alert = Alert(ts=1.0, kind='class', label='dos', alert_id='alert-1')
            sink.write(alert, ('key',), [{'frame.time_epoch': 1.0}])
            self.assertEqual(list(Path(directory).rglob('*.jsonl')), [])


if __name__ == '__main__':
    unittest.main()
