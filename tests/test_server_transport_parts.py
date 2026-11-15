"""Piezas del servidor de capturas, sin sockets reales."""

import asyncio
import unittest

from detection.infrastructure.transport.connection_limiter import ConnectionLimiter
from detection.infrastructure.transport.listener import listener_for
from detection.infrastructure.transport.sensor_auth import SensorAuth
from detection.infrastructure.transport.sensor_identity import SensorIdentity
from detection.infrastructure.transport.tls_listener import TlsListener
from detection.infrastructure.transport.unix_listener import UnixListener
from wire.protocol import HELLO_ACK_FRAME, hello_frame

CLAIMS = {'tenant_id': 't1', 'broker_id': 'b1', 'sensor_id': 's1', 'exp': 2000}


class FakeWriter:
    def __init__(self):
        self.data = b''

    def write(self, data):
        self.data += data

    async def drain(self):
        pass


def _reader(*lines):
    reader = asyncio.StreamReader()
    for line in lines:
        reader.feed_data(line)
    reader.feed_eof()
    return reader


class SensorIdentityTests(unittest.TestCase):
    def test_from_claims(self):
        identity = SensorIdentity.from_claims(CLAIMS)
        self.assertEqual(identity.broker_id, 'b1')
        self.assertEqual(identity.expires_at, 2000.0)
        self.assertIsNone(SensorIdentity.from_claims({**CLAIMS, 'exp': 'x'}).expires_at)
        with self.assertRaises(KeyError):
            SensorIdentity.from_claims({'tenant_id': 't1'})

    def test_bind_fills_missing_ids_and_rejects_spoofing(self):
        identity = SensorIdentity.from_claims(CLAIMS)
        record = {'broker_id': 'b1'}
        self.assertTrue(identity.bind(record))
        self.assertEqual(record['sensor_id'], 's1')
        self.assertFalse(identity.bind({'broker_id': 'otro'}))

    def test_remaining(self):
        self.assertEqual(SensorIdentity.from_claims(CLAIMS).remaining(1500), 500)
        self.assertIsNone(SensorIdentity('t', 'b', 's').remaining(1500))


class SensorAuthTests(unittest.TestCase):
    def _run(self, auth, *lines):
        writer = FakeWriter()

        async def go():
            return await auth.authenticate(_reader(*lines), writer)

        return asyncio.run(go()), writer

    def test_valid_hello_is_acknowledged(self):
        auth = SensorAuth(lambda token: CLAIMS, require_token=True)
        identity, writer = self._run(auth, hello_frame('tok'))
        self.assertEqual(identity.sensor_id, 's1')
        self.assertEqual(writer.data, HELLO_ACK_FRAME)

    def test_rejections_send_no_ack(self):
        def invalid(token):
            raise ValueError('bad')

        cases = [
            (SensorAuth(invalid, require_token=True), hello_frame('tok')),
            (SensorAuth(lambda t: {'tenant_id': 't'}, require_token=True), hello_frame('tok')),
            (SensorAuth(lambda t: CLAIMS, require_token=True), b'{"frame.len": 1}\n'),
            (SensorAuth(None, require_token=True), hello_frame('tok')),
            (SensorAuth(lambda t: CLAIMS, require_token=True), b''),
        ]
        for auth, line in cases:
            identity, writer = self._run(auth, line)
            self.assertIsNone(identity, line)
            self.assertEqual(writer.data, b'')

    def test_required_flag(self):
        self.assertFalse(SensorAuth().required)
        self.assertTrue(SensorAuth(lambda t: CLAIMS, require_token=True).required)


class ConnectionLimiterTests(unittest.TestCase):
    def test_admits_up_to_max_and_cancels_all(self):
        async def go():
            limiter = ConnectionLimiter(2)
            tasks = [asyncio.create_task(asyncio.sleep(10)) for _ in range(3)]
            admitted = [limiter.admit(task) for task in tasks]
            self.assertEqual(admitted, [True, True, False])
            self.assertEqual(limiter.rejected, 1)
            limiter.release(tasks[0])
            self.assertEqual(len(limiter), 1)
            await limiter.cancel_all()
            self.assertTrue(tasks[1].cancelled())
            tasks[0].cancel()
            tasks[2].cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        asyncio.run(go())


class ListenerForTests(unittest.TestCase):
    def test_selects_listener_by_scheme(self):
        self.assertIsInstance(listener_for('unix:///tmp/x.sock'), UnixListener)
        self.assertIsInstance(listener_for('/tmp/x.sock'), UnixListener)
        tls = listener_for('tls://0.0.0.0:8443')
        self.assertIsInstance(tls, TlsListener)
        self.assertEqual((tls.host, tls.port), ('0.0.0.0', 8443))

    def test_tls_without_context_fails_on_open(self):
        async def go():
            await TlsListener('127.0.0.1', 0, None).open(None, 1024, 10)

        with self.assertRaises(ValueError):
            asyncio.run(go())


if __name__ == '__main__':
    unittest.main()
