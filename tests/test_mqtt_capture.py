import unittest

from detection.infrastructure.tshark.stream_features import (
    CAPTURE_FIELDS, RECORD_FIELDS, build_command, build_display_filter,
    parse_args, record_from_fields, wire_record,
)

SENSITIVE = {'mqtt.passwd', 'mqtt.username', 'mqtt.msg',
             'mqtt.willmsg', 'mqtt.willtopic'}


def _record(**values):
    return record_from_fields(
        [values.get(field, '') for field in CAPTURE_FIELDS])


class CaptureTests(unittest.TestCase):
    def test_capture_requests_only_minimal_safe_fields(self):
        command = build_command(parse_args([]))
        self.assertNotIn('-Y', command)
        for field in CAPTURE_FIELDS:
            self.assertIn(field, command)
        for field in SENSITIVE:
            self.assertNotIn(field, command)

    def test_display_filter_excludes_topic(self):
        self.assertEqual(build_display_filter('', 'alertas/deteccion'),
                         '!(mqtt.topic == "alertas/deteccion")')

    def test_wire_record_has_no_sensitive_fields(self):
        record = _record(**{
            'frame.time_epoch': '1762624800.5',
            'frame.time_delta': '0.1',
            'frame.len': '66',
            'ip.src': '10.0.0.1',
            'ip.dst': '10.0.0.2',
            'tcp.srcport': '40000',
            'tcp.dstport': '1883',
            'tcp.stream': '7',
            'mqtt.msgtype': '3',
            'mqtt.clientid': 'sensor1',
            'mqtt.topic': 'home/temp',
        })
        wire = wire_record(record, {'frame.len': 66.0})
        self.assertEqual(set(wire), set(RECORD_FIELDS))
        self.assertNotIn('mqtt.msgtype', wire)
        self.assertFalse(SENSITIVE & set(wire))
        self.assertEqual(wire['tcp_features'], {'frame.len': 66.0})
        self.assertEqual(wire['frame.time_epoch'], 1762624800.5)
        self.assertEqual(wire['tcp.stream'], 7)

    def test_wire_record_carries_identity(self):
        record = _record(**{'tcp.stream': '7'})
        wire = wire_record(record, {'frame.len': 1.0}, {
            'tenant_id': 't1', 'broker_id': 'b1', 'sensor_id': 's1'})
        self.assertEqual(wire['tenant_id'], 't1')
        self.assertEqual(wire['broker_id'], 'b1')
        self.assertEqual(wire['sensor_id'], 's1')

    def test_missing_fields_are_null(self):
        record = _record(**{'tcp.stream': '7'})
        self.assertIsNone(record['ip.src'])
        self.assertEqual(record['tcp.stream'], 7)


if __name__ == '__main__':
    unittest.main()
