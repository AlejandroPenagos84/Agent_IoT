"""S1/S2: revocación de sensores en el socket, tope por sensor e inactividad."""

import asyncio
import socket
import threading
import time
import unittest

from capture.infrastructure.transport.drop_oldest_queue import DropOldestQueue
from capture.infrastructure.transport.sender_stats import SenderStats
from capture.infrastructure.transport.socket_sender import SocketSender
from capture.infrastructure.transport.token_auth import TokenAuth
from detection.infrastructure.repositories.registry_sqlite import RegistryStore, connect
from detection.infrastructure.transport.connection_limiter import SensorSlots
from detection.infrastructure.transport.sensor_auth import SensorAuth
from detection.infrastructure.transport.sensor_connection import SensorConnection
from detection.infrastructure.transport.sensor_identity import SensorIdentity
from wire.protocol import HELLO_ACK_FRAME, PING_FRAME, hello_frame

CLAIMS = {'tenant_id': 't1', 'broker_id': 'b1', 'sensor_id': 's1', 'iat': 1000}
RECORD = b'{"tcp.stream": 1, "tcp_features": {"frame.len": 1}}\n'


class FakeWriter:
    def __init__(self):
        self.data = b''
        self.closed = False

    def write(self, data):
        self.data += data

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


class RegistryRevocationTests(unittest.TestCase):
    def setUp(self):
        self.store = RegistryStore(connect(':memory:'))
        self.broker = self.store.create_broker('t1', 'b')
        self.sensor = self.store.enroll_sensor(self.broker, 'cap', 'hash-1')
        self.ids = ('t1', self.broker['id'], self.sensor['id'])

    def test_enrolled_sensor_is_active(self):
        self.assertTrue(self.store.sensor_token_active(*self.ids, issued_at=1.0))

    def test_wrong_ids_are_not_active(self):
        self.assertFalse(
            self.store.sensor_token_active('t2', self.ids[1], self.ids[2], issued_at=1.0)
        )
        self.assertFalse(self.store.sensor_token_active('t1', 'otro', self.ids[2], 1.0))

    def test_key_rotation_revokes_older_tokens(self):
        before = time.time() - 5
        self.store.set_enrollment_key('t1', self.broker['id'], 'nueva')
        self.assertFalse(self.store.sensor_token_active(*self.ids, issued_at=before))
        self.assertFalse(self.store.sensor_token_active(*self.ids, issued_at=None))
        # Un token emitido después (p. ej. inscribiendo de nuevo) sí vale.
        self.assertTrue(self.store.sensor_token_active(*self.ids, issued_at=time.time() + 1))

    def test_reinstall_revokes_previous_installation(self):
        before = time.time() - 5
        self.store.enroll_sensor(self.broker, 'cap', 'hash-2')
        self.assertFalse(self.store.sensor_token_active(*self.ids, issued_at=before))
        # Token de la reinstalación, emitido en el mismo segundo (iat entero).
        self.assertTrue(self.store.sensor_token_active(*self.ids, issued_at=int(time.time())))

    def test_deleted_broker_revokes_sensor(self):
        self.store.delete_broker('t1', self.broker['id'])
        self.assertFalse(self.store.sensor_token_active(*self.ids, issued_at=1.0))


class SensorAuthActiveCheckTests(unittest.TestCase):
    def _run(self, is_active):
        async def go():
            reader = asyncio.StreamReader()
            reader.feed_data(hello_frame('tok'))
            writer = FakeWriter()
            auth = SensorAuth(lambda t: CLAIMS, require_token=True, is_active=is_active)
            return await auth.authenticate(reader, writer), writer.data

        return asyncio.run(go())

    def test_active_sensor_is_acknowledged(self):
        identity, sent = self._run(lambda identity: True)
        self.assertEqual(identity.sensor_id, 's1')
        self.assertEqual(identity.issued_at, 1000.0)
        self.assertEqual(sent, HELLO_ACK_FRAME)

    def test_revoked_sensor_gets_no_ack(self):
        identity, sent = self._run(lambda identity: False)
        self.assertIsNone(identity)
        self.assertEqual(sent, b'')

    def test_registry_failure_fails_closed(self):
        def broken(identity):
            raise RuntimeError('db caída')

        identity, sent = self._run(broken)
        self.assertIsNone(identity)
        self.assertEqual(sent, b'')


class SensorSlotsTests(unittest.TestCase):
    def test_caps_each_sensor_independently(self):
        slots = SensorSlots(2)
        self.assertTrue(slots.acquire('s1'))
        self.assertTrue(slots.acquire('s1'))
        self.assertFalse(slots.acquire('s1'))
        self.assertTrue(slots.acquire('s2'))
        self.assertEqual(slots.rejected, 1)
        slots.release('s1')
        self.assertTrue(slots.acquire('s1'))
        slots.release('s1')
        slots.release('s1')
        self.assertEqual(slots.count('s1'), 0)


class SensorConnectionLimitsTests(unittest.TestCase):
    def _serve(self, *, is_active=lambda i: True, slots=None, feed_after=None, **kwargs):
        """Atiende una conexión que manda hello + un registro y luego se queda callada."""
        routed = []

        async def route(frame):
            routed.append(frame)

        async def go():
            reader = asyncio.StreamReader()
            reader.feed_data(hello_frame('tok') + RECORD)
            writer = FakeWriter()
            auth = SensorAuth(lambda t: CLAIMS, require_token=True, is_active=is_active)
            connection = SensorConnection(
                reader,
                writer,
                auth=auth,
                route=route,
                max_line_bytes=65536,
                should_stop=lambda: False,
                sensor_slots=slots,
                **kwargs,
            )
            if feed_after is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(feed_after[0], reader.feed_data, feed_after[1])
            started = time.monotonic()
            await asyncio.wait_for(connection.serve(), timeout=5)
            return time.monotonic() - started, writer

        elapsed, writer = asyncio.run(go())
        return elapsed, writer, routed

    def test_idle_connection_is_closed(self):
        elapsed, writer, routed = self._serve(idle_timeout=0.2)
        self.assertEqual(len(routed), 1)
        self.assertTrue(writer.closed)
        self.assertLess(elapsed, 2)

    def test_ping_keeps_connection_alive(self):
        # Ping a los 0.15 s: sin él cerraría a los 0.2 s; con él, a los ~0.35 s.
        elapsed, _, routed = self._serve(idle_timeout=0.2, feed_after=(0.15, PING_FRAME))
        self.assertEqual(len(routed), 1)  # el ping no se enruta
        self.assertGreater(elapsed, 0.3)

    def test_revocation_disconnects_open_connection(self):
        state = {'active': True}
        timer = threading.Timer(0.1, lambda: state.update(active=False))
        timer.start()
        elapsed, writer, routed = self._serve(
            is_active=lambda identity: state['active'], idle_timeout=None, recheck_seconds=0.2
        )
        timer.cancel()
        self.assertEqual(len(routed), 1)
        self.assertTrue(writer.closed)
        self.assertLess(elapsed, 2)

    def test_sensor_over_its_quota_is_refused_and_slot_released(self):
        slots = SensorSlots(1)
        slots.acquire('s1')  # otra conexión del mismo sensor ya abierta
        _, writer, routed = self._serve(slots=slots, idle_timeout=0.2)
        self.assertEqual(routed, [])
        self.assertTrue(writer.closed)
        self.assertEqual(slots.count('s1'), 1)

        slots.release('s1')
        self._serve(slots=slots, idle_timeout=0.1)
        self.assertEqual(slots.count('s1'), 0)  # se libera al cerrar


class ObservedSocket:
    """Lado servidor de un socketpair: acumula lo que manda el sender."""

    def __init__(self):
        self.client, self.server = socket.socketpair()
        self.server.settimeout(5)

    def open(self, timeout):
        return self.client


class SenderKeepaliveTests(unittest.TestCase):
    def test_sender_pings_when_idle(self):
        peer = ObservedSocket()
        stats = SenderStats(interval=999)
        sender = SocketSender(
            peer,
            TokenAuth.static(None),
            DropOldestQueue(10, on_drop=stats.on_dropped),
            stats,
            keepalive_seconds=0.2,
        )
        sender.start()
        try:
            data = peer.server.recv(1024)
        finally:
            sender.close(0.1)
            peer.server.close()
        self.assertTrue(data.startswith(PING_FRAME))


class SensorIdentityIssuedAtTests(unittest.TestCase):
    def test_issued_at_is_optional(self):
        self.assertIsNone(SensorIdentity.from_claims({**CLAIMS, 'iat': 'x'}).issued_at)


if __name__ == '__main__':
    unittest.main()
