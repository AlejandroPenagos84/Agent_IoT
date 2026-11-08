import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from detection.domain.model import Alert
from detection.infrastructure.sinks import HttpAlertSink


class _Handler(BaseHTTPRequestHandler):
    records = []

    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length)
        type(self).records.append((dict(self.headers), json.loads(body)))
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b'{"stored": true}')

    def log_message(self, *args):
        pass


def _wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class HttpAlertSinkTests(unittest.TestCase):
    def setUp(self):
        _Handler.records = []
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/v1/alerts'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def test_posts_alert_with_bearer_token(self):
        sink = HttpAlertSink(self.url, 'token-1')
        alert = Alert(ts=1_800_000_000, kind='class', label='ataque',
                      tenant_id='t1', broker_id='b1', sensor_id='s1',
                      alert_id='a1')
        sink.emit(alert)
        self.assertTrue(_wait_for(lambda: sink.stats['sent'] == 1))
        sink.close()
        headers, body = _Handler.records[0]
        self.assertEqual(headers['Authorization'], 'Bearer token-1')
        self.assertEqual(headers['Content-Type'], 'application/json')
        self.assertEqual(body['alert_id'], 'a1')
        self.assertEqual(body['tenant_id'], 't1')
        self.assertEqual(body['broker_id'], 'b1')
        self.assertEqual(body['sensor_id'], 's1')

    def test_failure_is_counted_without_raising(self):
        sink = HttpAlertSink('http://127.0.0.1:1/api/v1/alerts', 'token',
                             timeout=0.2, retries=1)
        sink.emit(Alert(ts=1.0, kind='class', label='ataque', alert_id='a2'))
        self.assertTrue(_wait_for(lambda: sink.stats['failed'] == 1))
        sink.close(2.0)
        self.assertEqual(sink.stats['sent'], 0)
        self.assertEqual(sink.stats['failed'], 1)


if __name__ == '__main__':
    unittest.main()
