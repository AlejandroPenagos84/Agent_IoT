import io
import socket
import ssl
import unittest

from capture.infrastructure.transport.connector import connector_for
from capture.infrastructure.transport.drop_oldest_queue import DropOldestQueue
from capture.infrastructure.transport.sender_stats import SenderStats
from capture.infrastructure.transport.tls_connector import TlsConnector
from capture.infrastructure.transport.token_auth import TokenAuth
from capture.infrastructure.transport.unix_connector import UnixConnector
from wire.protocol import HELLO_ACK_FRAME


class TokenAuthTests(unittest.TestCase):
    def test_static_without_token_never_pauses_or_reconnects(self):
        auth = TokenAuth.static(None)

        self.assertFalse(auth.paused())
        self.assertFalse(auth.changed())

    def test_dynamic_pauses_when_revoked_and_detects_renewal(self):
        current = {'token': 'a'}
        auth = TokenAuth(lambda: current['token'])

        server, client = socket.socketpair()
        server.sendall(HELLO_ACK_FRAME)
        auth.handshake(client)
        self.assertIn(b'"token": "a"', server.recv(1024))
        server.close()
        client.close()

        self.assertFalse(auth.changed())

        current['token'] = 'b'
        self.assertTrue(auth.changed())

        current['token'] = None
        self.assertTrue(auth.paused())

    def test_handshake_without_ack_raises(self):
        auth = TokenAuth.static('tok')

        server, client = socket.socketpair()
        server.sendall(b'{"type":"error"}\n')

        with self.assertRaises(ConnectionError):
            auth.handshake(client)

        server.close()
        client.close()


class DropOldestQueueTests(unittest.TestCase):
    def test_full_queue_drops_oldest_and_counts(self):
        queue = DropOldestQueue(2)

        for item in ('a', 'b', 'c'):
            queue.put(item)

        self.assertEqual(queue.dropped, 1)
        self.assertEqual(queue.take(10), ['b', 'c'])
        self.assertFalse(queue.wait(0.01))


class SenderStatsTests(unittest.TestCase):
    def test_first_connection_is_not_a_reconnect(self):
        stats = SenderStats(sink=io.StringIO())

        stats.on_connected()
        stats.on_connected()
        stats.on_sent(3)
        stats.on_dropped(1)

        self.assertEqual(
            stats.snapshot(extra_dropped=2), {'sent': 3, 'dropped': 3, 'reconnects': 1}
        )

    def test_report_prints_only_the_delta(self):
        sink = io.StringIO()
        stats = SenderStats(sink=sink)

        stats.on_sent(5)
        stats.report()
        stats.on_sent(2)
        stats.report()

        lines = sink.getvalue().splitlines()
        self.assertIn('"sent": 5', lines[0])
        self.assertIn('"sent": 2', lines[1])


class ConnectorForTests(unittest.TestCase):
    def test_picks_adapter_by_scheme(self):
        self.assertIsInstance(connector_for('/tmp/x.sock'), UnixConnector)
        self.assertIsInstance(connector_for('unix:///tmp/x.sock'), UnixConnector)

        context = ssl.create_default_context()
        connector = connector_for('tls://agent.example.com:8443', context, 'agent')
        self.assertIsInstance(connector, TlsConnector)
        self.assertEqual((connector.host, connector.port), ('agent.example.com', 8443))

    def test_tls_without_context_fails_fast(self):
        with self.assertRaises(ValueError):
            connector_for('tls://agent.example.com:8443')


if __name__ == '__main__':
    unittest.main()
