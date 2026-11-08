import asyncio
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from detection.application import Agent, BrokerPool, DetectionServer
from detection.application.ports.ports_out import AlertSink, Classifier
from detection.application.ports.types import Frame
from detection.application.use_cases.broker_pool import QueueFeatureSource
from detection.domain.model import FrameContext
from detection.infrastructure.tshark.async_socket_server import AsyncSocketServer
from detection.infrastructure.tshark.socket_sender import SocketSender


def make_certs(directory):
    """Create a throwaway CA and a server certificate for localhost."""
    if shutil.which('openssl') is None:
        raise unittest.SkipTest('openssl no está instalado')
    root = Path(directory)
    ca_key, ca_crt = root / 'ca.key', root / 'ca.crt'
    server_key, server_csr = root / 'server.key', root / 'server.csr'
    server_crt, ext = root / 'server.crt', root / 'server.ext'
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', str(ca_key), '-out', str(ca_crt), '-days', '1',
        '-subj', '/CN=test-ca',
        '-addext', 'basicConstraints=critical,CA:TRUE',
        '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
        '-addext', 'subjectKeyIdentifier=hash',
    ], check=True, capture_output=True)
    subprocess.run(['openssl', 'req', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(server_key), '-out', str(server_csr),
                    '-subj', '/CN=localhost'], check=True, capture_output=True)
    ext.write_text('subjectAltName=DNS:localhost,IP:127.0.0.1\n')
    subprocess.run(['openssl', 'x509', '-req', '-in', str(server_csr),
                    '-CA', str(ca_crt), '-CAkey', str(ca_key),
                    '-CAcreateserial', '-out', str(server_crt), '-days', '1',
                    '-extfile', str(ext)], check=True, capture_output=True)
    return ca_crt, server_crt, server_key


def tls_validator(token):
    if token != 'good':
        raise ValueError('token inválido')
    return {'tenant_id': 't1', 'broker_id': 'b1', 'sensor_id': 's1'}



def feature_record(index, stream=1, tenant='t1', broker='b1', sensor='s1'):
    return {
        'frame.time_epoch': float(index),
        'frame.time_delta': 0.1,
        'frame.len': 66.0,
        'ip.src': '10.0.0.1',
        'ip.dst': '10.0.0.2',
        'tcp.srcport': 40000,
        'tcp.dstport': 1883,
        'tcp.stream': stream,
        'mqtt.clientid': 'sensor1',
        'mqtt.topic': 'home/temp',
        'tenant_id': tenant,
        'broker_id': broker,
        'sensor_id': sensor,
        'tcp_features': {'frame.len': 66.0, 'tcp_frames_5s': float(index)},
    }


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class Collector:
    def __init__(self, target=None):
        self.frames = []
        self.target = target
        self.done = threading.Event()
        self._lock = threading.Lock()

    async def route(self, frame):
        with self._lock:
            self.frames.append(frame)
            if self.target is not None and len(self.frames) >= self.target:
                self.done.set()

    def snapshot(self):
        with self._lock:
            return list(self.frames)


class AlwaysAttack(Classifier):
    def predict(self, window):
        return ['ataque'] * len(window)


class AlertRecorder(AlertSink):
    def __init__(self):
        self.alerts = []
        self._lock = threading.Lock()

    def emit(self, alert):
        with self._lock:
            self.alerts.append(alert)

    def snapshot(self):
        with self._lock:
            return list(self.alerts)


def make_pool(**kwargs):
    alerts = AlertRecorder()

    def factory(source):
        return Agent(source, AlwaysAttack(), alerts, window_size=1,
                     alert_cooldown=0)

    return BrokerPool(factory, **kwargs), alerts


def start_server(directory, collector, **kwargs):
    path = str(Path(directory) / 'features.sock')
    server = AsyncSocketServer(path, **kwargs)
    server.start(collector.route)
    return server, path


def connect(path):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(5)
    client.connect(path)
    return client


class SocketSenderTests(unittest.TestCase):
    def test_queue_is_bounded_and_counts_drops(self):
        sender = SocketSender('/tmp/does-not-exist.sock', queue_size=10,
                              retry_seconds=0.01, stats_seconds=999)
        for index in range(100):
            sender.send(json.dumps(feature_record(index)) + '\n')
        self.assertEqual(len(sender._queue), 10)
        self.assertEqual(sender.stats['dropped'], 90)

    def test_sender_delivers_in_order_to_server(self):
        collector = Collector(target=5)
        with tempfile.TemporaryDirectory(prefix='iot-sock-') as directory:
            server, path = start_server(directory, collector)
            sender = SocketSender(path, retry_seconds=0.01)
            sender.start()
            for index in range(5):
                sender.send(json.dumps(feature_record(index)) + '\n')
            self.assertTrue(collector.done.wait(5))
            sender.close(0.5)
            server.stop()
        self.assertEqual([frame.features['tcp_frames_5s']
                          for frame in collector.snapshot()],
                         [0.0, 1.0, 2.0, 3.0, 4.0])
        self.assertEqual(collector.snapshot()[0].context.sensor_id, 's1')

    def test_sender_connects_when_server_appears_later(self):
        collector = Collector(target=1)
        with tempfile.TemporaryDirectory(prefix='iot-late-') as directory:
            path = str(Path(directory) / 'features.sock')
            sender = SocketSender(path, retry_seconds=0.01)
            sender.start()
            sender.send(json.dumps(feature_record(0)) + '\n')
            time.sleep(0.1)
            server, path = start_server(directory, collector)
            self.assertTrue(collector.done.wait(5))
            sender.close(0.5)
            server.stop()
        self.assertEqual(len(collector.snapshot()), 1)

    def test_close_drains_queue(self):
        collector = Collector(target=3)
        with tempfile.TemporaryDirectory(prefix='iot-drain-') as directory:
            server, path = start_server(directory, collector)
            sender = SocketSender(path, retry_seconds=0.01)
            sender.start()
            for index in range(3):
                sender.send(json.dumps(feature_record(index)) + '\n')
            sender.close(2.0)
            self.assertTrue(collector.done.wait(2))
            server.stop()
        self.assertEqual(len(collector.snapshot()), 3)


class AsyncSocketServerTests(unittest.TestCase):
    def test_partial_lines_and_invalid_json_are_handled(self):
        collector = Collector(target=2)
        with tempfile.TemporaryDirectory(prefix='iot-partial-') as directory:
            server, path = start_server(directory, collector)
            client = connect(path)
            first = json.dumps(feature_record(0)) + '\n'
            client.sendall(first[:10].encode())
            client.sendall(first[10:].encode())
            client.sendall(b'{not json}\n')
            client.sendall((json.dumps(feature_record(1)) + '\n').encode())
            self.assertTrue(collector.done.wait(5))
            client.close()
            server.stop()
        self.assertEqual(len(collector.snapshot()), 2)
        self.assertEqual(collector.snapshot()[1].features['tcp_frames_5s'], 1.0)

    def test_multiple_clients_are_served(self):
        collector = Collector(target=2)
        with tempfile.TemporaryDirectory(prefix='iot-multi-') as directory:
            server, path = start_server(directory, collector)
            first = connect(path)
            second = connect(path)
            first.sendall((json.dumps(feature_record(0, sensor='s1')) + '\n').encode())
            second.sendall((json.dumps(feature_record(1, sensor='s2')) + '\n').encode())
            self.assertTrue(collector.done.wait(5))
            first.close()
            second.close()
            server.stop()
        sensors = {frame.context.sensor_id for frame in collector.snapshot()}
        self.assertEqual(sensors, {'s1', 's2'})

    def test_stop_finishes_and_removes_socket_file(self):
        collector = Collector()
        with tempfile.TemporaryDirectory(prefix='iot-stop-') as directory:
            server, path = start_server(directory, collector)
            started = time.monotonic()
            server.stop()
            self.assertLess(time.monotonic() - started, 5)
        self.assertFalse(os.path.exists(path))


class TlsSocketTests(unittest.TestCase):
    def _start_tls_server(self, directory, collector, **kwargs):
        ca, cert, key = make_certs(directory)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        server = AsyncSocketServer('tls://127.0.0.1:0', ssl_context=context,
                                   **kwargs)
        server.start(collector.route)
        return server, ca

    def test_tls_sender_server_and_identity_from_token(self):
        collector = Collector(target=1)
        with tempfile.TemporaryDirectory(prefix='iot-tls-') as directory:
            server, ca = self._start_tls_server(
                directory, collector, token_validator=tls_validator,
                require_token=True)
            try:
                client = ssl.create_default_context(cafile=str(ca))
                sender = SocketSender(
                    f'tls://127.0.0.1:{server.port}', tls_context=client,
                    server_name='localhost', sensor_token='good',
                    retry_seconds=0.05)
                sender.start()
                record = feature_record(0)
                for key in ('tenant_id', 'broker_id', 'sensor_id'):
                    record.pop(key)
                sender.send(json.dumps(record) + '\n')
                self.assertTrue(collector.done.wait(5))
                sender.close(0.5)
            finally:
                server.stop()
        frame = collector.snapshot()[0]
        self.assertEqual(frame.context.tenant_id, 't1')
        self.assertEqual(frame.context.broker_id, 'b1')
        self.assertEqual(frame.context.sensor_id, 's1')

    def test_tls_rejects_invalid_token(self):
        collector = Collector()
        with tempfile.TemporaryDirectory(prefix='iot-tls-bad-') as directory:
            server, ca = self._start_tls_server(
                directory, collector, token_validator=tls_validator,
                require_token=True)
            try:
                client = ssl.create_default_context(cafile=str(ca))
                sender = SocketSender(
                    f'tls://127.0.0.1:{server.port}', tls_context=client,
                    server_name='localhost', sensor_token='bad',
                    retry_seconds=0.05)
                sender.start()
                sender.send(json.dumps(feature_record(0)) + '\n')
                time.sleep(0.5)
                self.assertEqual(collector.snapshot(), [])
                sender.close(0.2)
            finally:
                server.stop()

    def test_tls_rejects_identity_spoofing(self):
        collector = Collector()
        with tempfile.TemporaryDirectory(prefix='iot-tls-spoof-') as directory:
            server, ca = self._start_tls_server(
                directory, collector, token_validator=tls_validator,
                require_token=True)
            try:
                client = ssl.create_default_context(cafile=str(ca))
                sender = SocketSender(
                    f'tls://127.0.0.1:{server.port}', tls_context=client,
                    server_name='localhost', sensor_token='good',
                    retry_seconds=0.05)
                sender.start()
                sender.send(json.dumps(feature_record(0, broker='b2')) + '\n')
                time.sleep(0.5)
                self.assertEqual(collector.snapshot(), [])
                sender.close(0.2)
            finally:
                server.stop()


    def test_renewed_token_reconnects_and_expired_token_disconnects(self):
        collector = Collector(target=2)
        hellos = []

        def validator(token):
            hellos.append(token)
            exp = time.time() + (0.6 if token == 'short' else 60)
            return {'tenant_id': 't1', 'broker_id': 'b1', 'sensor_id': 's1',
                    'exp': exp}

        current = {'token': 'short'}
        with tempfile.TemporaryDirectory(prefix='iot-tls-renew-') as directory:
            server, ca = self._start_tls_server(
                directory, collector, token_validator=validator,
                require_token=True)
            try:
                client = ssl.create_default_context(cafile=str(ca))
                sender = SocketSender(
                    f'tls://127.0.0.1:{server.port}', tls_context=client,
                    server_name='localhost', retry_seconds=0.05,
                    token_provider=lambda: current['token'])
                sender.start()
                sender.send(json.dumps(feature_record(0)) + '\n')
                self.assertTrue(wait_for(lambda: len(collector.snapshot()) == 1))
                current['token'] = 'long'
                time.sleep(0.3)
                sender.send(json.dumps(feature_record(1)) + '\n')
                self.assertTrue(collector.done.wait(5))
                self.assertEqual(hellos[:2], ['short', 'long'])
                current['token'] = None  # revoked: sender pauses
                time.sleep(0.3)
                sender.send(json.dumps(feature_record(2)) + '\n')
                time.sleep(0.4)
                self.assertEqual(len(collector.snapshot()), 2)
                sender.close(0.2)
            finally:
                server.stop()

    def test_server_closes_connection_at_token_expiry(self):
        collector = Collector()

        def validator(token):
            return {'tenant_id': 't1', 'broker_id': 'b1', 'sensor_id': 's1',
                    'exp': time.time() + 0.3}

        with tempfile.TemporaryDirectory(prefix='iot-tls-exp-') as directory:
            server, ca = self._start_tls_server(
                directory, collector, token_validator=validator,
                require_token=True)
            try:
                client = ssl.create_default_context(cafile=str(ca))
                raw = socket.create_connection(('127.0.0.1', server.port), 5)
                sock = client.wrap_socket(raw, server_hostname='localhost')
                sock.sendall(b'{"type":"hello","token":"x"}\n')
                sock.settimeout(3)
                self.assertIn(b'hello_ack', sock.recv(1024))
                started = time.time()
                self.assertEqual(sock.recv(1024), b'')  # closed by server
                self.assertLess(time.time() - started, 2)
                sock.close()
            finally:
                server.stop()


class BrokerPoolTests(unittest.TestCase):
    def test_one_worker_per_broker(self):
        pool, alerts = make_pool(max_workers=4, queue_size=10)
        now = time.time()
        asyncio.run(pool.route(Frame({}, FrameContext(
            ts=now, ip='10.0.0.1', dst_ip='10.0.0.2', srcport=1,
            dstport=1883, stream_id=1, tenant_id='t', broker_id='b1',
            sensor_id='s1'))))
        asyncio.run(pool.route(Frame({}, FrameContext(
            ts=now, ip='10.0.0.1', dst_ip='10.0.0.2', srcport=2,
            dstport=1883, stream_id=1, tenant_id='t', broker_id='b2',
            sensor_id='s1'))))
        self.assertTrue(wait_for(lambda: len(alerts.snapshot()) == 2))
        self.assertEqual(len(pool), 2)
        pool.stop()
        self.assertEqual({alert.broker_id for alert in alerts.snapshot()},
                         {'b1', 'b2'})

    def test_same_broker_shares_worker(self):
        pool, alerts = make_pool(max_workers=4, queue_size=10)
        now = time.time()
        for port in (1, 2):
            asyncio.run(pool.route(Frame({}, FrameContext(
                ts=now, ip='10.0.0.1', dst_ip='10.0.0.2', srcport=port,
                dstport=1883, stream_id=port, tenant_id='t', broker_id='b1',
                sensor_id='s1'))))
        self.assertTrue(wait_for(lambda: len(alerts.snapshot()) == 2))
        self.assertEqual(len(pool), 1)
        pool.stop()

    def test_idle_workers_are_evicted(self):
        pool, alerts = make_pool(max_workers=4, queue_size=10,
                                 idle_seconds=0.05, reap_interval=0.02)
        pool.start()
        asyncio.run(pool.route(Frame({}, FrameContext(
            ts=time.time(), ip='10.0.0.1', dst_ip='10.0.0.2', srcport=1,
            dstport=1883, stream_id=1, tenant_id='t', broker_id='b1',
            sensor_id='s1'))))
        self.assertTrue(wait_for(lambda: len(alerts.snapshot()) == 1))
        self.assertTrue(wait_for(lambda: len(pool) == 0))
        pool.stop()


class QueueFeatureSourceTests(unittest.TestCase):
    def test_full_queue_reports_backpressure_instead_of_dropping(self):
        source = QueueFeatureSource(queue_size=1)
        source.start()
        first = Frame({'marker': 1}, FrameContext(ts=1.0))
        second = Frame({'marker': 2}, FrameContext(ts=2.0))
        self.assertTrue(source.submit(first))
        self.assertFalse(source.submit(second))
        rows = source.rows()
        self.assertEqual(next(rows).features['marker'], 1)
        self.assertTrue(source.submit(second))
        source.stop()


class EndToEndTests(unittest.TestCase):
    def test_two_brokers_are_detected_independently(self):
        pool, alerts = make_pool(max_workers=4, queue_size=10)
        with tempfile.TemporaryDirectory(prefix='iot-e2e-') as directory:
            path = str(Path(directory) / 'features.sock')
            server = AsyncSocketServer(path)
            detection = DetectionServer(server, pool)
            thread = threading.Thread(target=detection.run, daemon=True)
            thread.start()
            self.assertTrue(wait_for(lambda: os.path.exists(path)))
            sender = SocketSender(path, retry_seconds=0.01)
            sender.start()
            sender.send(json.dumps(feature_record(0, broker='b1')) + '\n')
            sender.send(json.dumps(feature_record(1, broker='b2')) + '\n')
            self.assertTrue(wait_for(lambda: len(alerts.snapshot()) == 2))
            sender.close(0.5)
            detection.stop()
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual({alert.broker_id for alert in alerts.snapshot()},
                         {'b1', 'b2'})


if __name__ == '__main__':
    unittest.main()
