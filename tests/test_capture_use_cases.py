"""Casos de uso de la captura con puertos falsos: sin red, sin disco y sin tshark."""

import json
import unittest

from capture.application.errors import EnrollmentError
from capture.application.ports import EnrollmentApi, PacketSource, RecordSender, SensorStateStore
from capture.application.use_cases import EnrollSensor, RefreshSensorToken, StreamFeatures
from capture.domain.sensor_state import key_digest
from capture.infrastructure.tshark import CAPTURE_FIELDS, record_from_fields

KEY = 'ek_test'


class FakeApi(EnrollmentApi):
    def __init__(self, expires_in=3600):
        self.expires_in = expires_in
        self.enrolls = 0
        self.refreshes = 0
        self.reject_refresh = False
        self.token_seq = 0

    def _token(self):
        self.token_seq += 1
        return {'access_token': f'tok-{self.token_seq}', 'expires_in': self.expires_in}

    def enroll(self, enrollment_key, name):
        if enrollment_key != KEY and not enrollment_key.startswith('ek_new'):
            raise EnrollmentError('HTTP 401')
        self.enrolls += 1
        return {
            'tenant_id': 't1',
            'broker_id': 'b1',
            'sensor_id': f's{self.enrolls}',
            'sensor_secret': 'secret',
            'agent_endpoint': 'tls://agent:8443',
            'agent_server_name': 'agent',
            'agent_ca': 'PEM',
            **self._token(),
        }

    def refresh(self, sensor_secret):
        self.refreshes += 1
        if self.reject_refresh:
            raise EnrollmentError('HTTP 401')
        return self._token()


class MemoryStore(SensorStateStore):
    def __init__(self):
        self.state = None
        self.ca = None
        self.saves = 0

    def load(self):
        return self.state

    def save(self, state):
        self.state = state
        self.saves += 1

    def save_ca(self, pem):
        self.ca = pem

    @property
    def ca_path(self):
        return '/ca' if self.ca else None


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _enrollment():
    api, store, clock = FakeApi(), MemoryStore(), Clock()
    refresh = RefreshSensorToken(api, store, clock=clock)
    return api, store, clock, refresh, EnrollSensor(api, store, refresh, clock=clock)


class EnrollSensorTests(unittest.TestCase):
    def test_first_start_enrolls_and_persists(self):
        api, store, _, _, enroll = _enrollment()
        state = enroll.execute(KEY, 'host')
        self.assertEqual(api.enrolls, 1)
        self.assertIs(store.state, state)
        self.assertEqual(store.ca, 'PEM')
        self.assertEqual(state.enrollment_key_sha256, key_digest(KEY))
        self.assertEqual(state.expires_at, 1000.0 + 3600)

    def test_restart_reuses_identity_with_a_refresh(self):
        api, _, _, _, enroll = _enrollment()
        first = enroll.execute(KEY, 'host')
        second = enroll.execute(KEY, 'host')
        self.assertEqual(first.sensor_id, second.sensor_id)
        self.assertEqual((api.enrolls, api.refreshes), (1, 1))

    def test_revoked_state_with_same_key_is_rejected(self):
        api, store, _, _, enroll = _enrollment()
        enroll.execute(KEY, 'host')
        store.state.revoked = True
        with self.assertRaises(EnrollmentError):
            enroll.execute(KEY, 'host')
        self.assertEqual(api.enrolls, 1)

    def test_rejected_refresh_on_restart_does_not_reenroll(self):
        api, store, _, _, enroll = _enrollment()
        enroll.execute(KEY, 'host')
        api.reject_refresh = True
        with self.assertRaises(EnrollmentError):
            enroll.execute(KEY, 'host')
        self.assertTrue(store.state.revoked)
        self.assertEqual(api.enrolls, 1)

    def test_new_key_reenrolls(self):
        api, store, _, _, enroll = _enrollment()
        enroll.execute(KEY, 'host')
        store.state.revoked = True
        state = enroll.execute('ek_new', 'host')
        self.assertEqual(api.enrolls, 2)
        self.assertFalse(state.revoked)

    def test_name_is_truncated(self):
        api, _, _, _, enroll = _enrollment()
        seen = []
        original = api.enroll
        api.enroll = lambda key, name: seen.append(name) or original(key, name)
        enroll.execute(KEY, 'x' * 300)
        self.assertEqual(len(seen[0]), 128)


class RefreshSensorTokenTests(unittest.TestCase):
    def test_token_changes_only_after_half_lifetime(self):
        _, store, clock, refresh, enroll = _enrollment()
        state = enroll.execute(KEY, 'host')
        original = state.access_token
        self.assertFalse(refresh.execute(state))
        self.assertEqual(state.access_token, original)
        clock.now += 1801
        saves = store.saves
        self.assertTrue(refresh.execute(state))
        self.assertNotEqual(state.access_token, original)
        self.assertEqual(state.issued_at, clock.now)
        self.assertEqual(store.saves, saves + 1)

    def test_rejection_marks_revoked(self):
        api, store, _, refresh, enroll = _enrollment()
        state = enroll.execute(KEY, 'host')
        api.reject_refresh = True
        with self.assertRaises(EnrollmentError):
            refresh.execute(state)
        self.assertTrue(store.state.revoked)


class ListSource(PacketSource):
    def __init__(self, records, returncode=0, interrupt=False):
        self._records = records
        self.returncode = returncode
        self.interrupt = interrupt
        self.closed = False

    def open(self):
        pass

    def records(self):
        yield from self._records
        if self.interrupt:
            raise KeyboardInterrupt

    def close(self):
        self.closed = True
        return self.returncode


class ListSender(RecordSender):
    def __init__(self):
        self.lines = []
        self.started = self.closed = False

    def start(self):
        self.started = True

    def send(self, line):
        self.lines.append(line)

    def close(self, timeout=2.0):
        self.closed = True


def _frame(t, stream, clientid=None, msgtype='3', srcport='40000'):
    values = {
        'frame.time_epoch': str(t),
        'frame.time_delta': '0.1',
        'frame.len': '66',
        'ip.src': '10.0.0.1',
        'ip.dst': '10.0.0.2',
        'tcp.srcport': srcport,
        'tcp.dstport': '1883',
        'tcp.stream': str(stream),
        'mqtt.msgtype': msgtype,
        'mqtt.clientid': clientid or '',
    }
    return record_from_fields([values.get(field, '') for field in CAPTURE_FIELDS])


class StreamFeaturesTests(unittest.TestCase):
    def test_sends_ndjson_with_identity_and_features(self):
        source = ListSource([_frame(1.0, 7, 'sensor', msgtype='1'), _frame(1.1, 7)])
        sender = ListSender()
        code = StreamFeatures(
            source, sender, identity={'broker_id': 'b1', 'tenant_id': ''}
        ).execute()
        self.assertEqual(code, 0)
        self.assertTrue(sender.started and sender.closed and source.closed)
        self.assertTrue(sender.lines)
        for line in sender.lines:
            self.assertTrue(line.endswith('\n'))
            record = json.loads(line)
            self.assertEqual(record['broker_id'], 'b1')
            self.assertNotIn('tenant_id', record)  # identidad vacía no se envía
            self.assertIn('tcp_features', record)

    def test_excludes_agent_stream_after_its_connect(self):
        frames = [
            _frame(1.0, 9, 'agente-alertas', msgtype='1', srcport='41000'),
            _frame(1.1, 9, srcport='41000'),
        ]
        sender = ListSender()
        StreamFeatures(ListSource(frames), sender, exclude_client_id='agente-alertas').execute()
        self.assertEqual(sender.lines, [])

    def test_ctrl_c_closes_and_returns_source_code(self):
        source = ListSource([], returncode=2, interrupt=True)
        sender = ListSender()
        self.assertEqual(StreamFeatures(source, sender).execute(), 2)
        self.assertTrue(sender.closed and source.closed)


if __name__ == '__main__':
    unittest.main()
