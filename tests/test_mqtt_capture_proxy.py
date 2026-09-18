import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from infrastructure.tshark.stream_features import (
    FIELDS, build_command, build_display_filter, parse_args, record_from_fields,
)
from simulation.mqtt_proxy import PublishTransformer


def publish(topic, payload, qos=0):
    encoded = topic.encode()
    body = len(encoded).to_bytes(2, 'big') + encoded
    if qos:
        body += b'\x00\x01'
    body += payload.encode()
    remaining = len(body)
    length = bytearray()
    while True:
        byte = remaining % 128
        remaining //= 128
        length.append(byte | (128 if remaining else 0))
        if not remaining:
            break
    return bytes([0x30 | (qos << 1)]) + bytes(length) + body


class CaptureProxyTests(unittest.TestCase):
    def test_capture_selects_all_frames_by_default_and_all_csv_fields(self):
        command = build_command(parse_args([]))
        self.assertNotIn('-Y', command)
        with (Path(__file__).resolve().parents[1] / 'dataset' / 'DoS.csv').open() as handle:
            header = handle.readline()
        self.assertEqual(set(header.strip().split(',')) - {'type'}, set(FIELDS) - {'tcp.stream'})
        self.assertEqual(build_display_filter('', 'alertas/deteccion'),
                         '!(mqtt.topic == "alertas/deteccion")')

    def test_wire_payload_decodes_like_csv(self):
        record = record_from_fields(['34:30:30', '3'], ('mqtt.msg', 'mqtt.msgtype'))
        self.assertEqual(record['mqtt.msg'], '400')
        self.assertEqual(record['mqtt.msgtype'], '3')

    def test_proxy_handles_fragmented_and_coalesced_packets(self):
        transformer = PublishTransformer()
        original = publish('distance/ultrasonic1', '100', qos=1)
        unchanged = publish('light/rele1', '1')
        self.assertEqual(transformer.feed(original[:1]), b'')
        self.assertEqual(transformer.feed(original[1:5]), b'')
        transformed = transformer.feed(original[5:] + unchanged)
        self.assertEqual(transformed, publish('distance/ultrasonic1', '900', qos=1) + unchanged)
        self.assertEqual(len(transformed), len(original) + len(unchanged))
        self.assertEqual(transformer.modified, 1)

    def test_proxy_preserves_control_messages_and_multibyte_lengths(self):
        transformer = PublishTransformer()
        control = b'\xc0\x00'
        packet = publish('distance/ultrasonic1', '1' * 200)
        self.assertEqual(transformer.feed(control + packet),
                         control + publish('distance/ultrasonic1', '9' + '1' * 199))

    @unittest.skipUnless(shutil.which('tshark'), 'tshark no instalado')
    def test_actual_tshark_fields_and_payload(self):
        import csv
        registry = subprocess.run(['tshark', '-G', 'fields'], capture_output=True,
                                  text=True, check=True).stdout
        available = {line.split('\t')[2] for line in registry.splitlines()
                     if line.startswith('F\t') and len(line.split('\t')) > 2}
        fields = tuple(field for field in FIELDS if field in available)
        self.assertIn('mqtt.msg', fields)
        self.assertIn('mqtt.msgtype', fields)
        # Ethernet + IPv4 + TCP + PUBLISH; fixture generado solo en /tmp.
        payload = publish('distance/ultrasonic1', '400')
        ethernet = bytes.fromhex('00112233445566778899aabb0800')
        ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 40 + len(payload), 1, 0,
                         64, 6, 0, b'\x0a\x00\x00\x01', b'\x0a\x00\x00\x02')
        tcp = struct.pack('!HHIIBBHHH', 40000, 1883, 1, 1, 0x50, 0x18, 65535, 0, 0)
        packet = ethernet + ip + tcp + payload
        with tempfile.TemporaryDirectory(prefix='mqtt-pcap-') as directory:
            path = Path(directory) / 'fixture.pcap'
            path.write_bytes(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
                             + struct.pack('<IIII', 1, 0, len(packet), len(packet)) + packet)
            command = ['tshark', '-n', '-r', str(path), '-T', 'fields',
                       '-E', 'occurrence=f', '-E', 'quote=d']
            for field in fields:
                command.extend(('-e', field))
            result = subprocess.run(command, capture_output=True, text=True, check=True)
        values = next(csv.reader([result.stdout.rstrip('\n')], delimiter='\t'))
        record = record_from_fields(values, fields)
        self.assertEqual(record['mqtt.msg'], '400')
        self.assertEqual(record['mqtt.topic'], 'distance/ultrasonic1')
        self.assertEqual(record['mqtt.msgtype'], '3')
        self.assertEqual(record['ip.dst'], '10.0.0.2')


if __name__ == '__main__':
    unittest.main()
