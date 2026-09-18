"""Proxy MQTT local: modifica un PUBLISH en tránsito antes de llegar al broker.

No realiza ARP spoofing; el sensor se conecta explícitamente al proxy del lab.
"""
from __future__ import annotations

import select
import socket
import socketserver
from threading import Lock, Thread


class PublishTransformer:
    def __init__(self, topic='distance/ultrasonic1'):
        self.topic = topic.encode()
        self.buffer = bytearray()
        self.modified = 0

    def feed(self, data):
        self.buffer.extend(data)
        output = bytearray()
        while len(self.buffer) >= 2:
            remaining, multiplier, offset = 0, 1, 1
            while True:
                if offset >= len(self.buffer):
                    return bytes(output)
                value = self.buffer[offset]
                offset += 1
                remaining += (value & 127) * multiplier
                if not value & 128:
                    break
                if offset == 5:
                    raise ValueError('Remaining Length MQTT inválido')
                multiplier *= 128
            if remaining > 1024 * 1024:
                raise ValueError('El proxy de laboratorio admite mensajes de hasta 1 MiB')
            total = offset + remaining
            if len(self.buffer) < total:
                break
            packet = bytearray(self.buffer[:total])
            del self.buffer[:total]
            if packet[0] >> 4 == 3 and remaining >= 2:
                topic_len = int.from_bytes(packet[offset:offset + 2], 'big')
                start = offset + 2
                payload_start = start + topic_len
                if (packet[0] >> 1) & 3:
                    payload_start += 2  # packet identifier para QoS 1/2
                if packet[start:start + topic_len] == self.topic and payload_start < total:
                    # Misma longitud: cambia una lectura numérica, conserva framing/QoS.
                    if 48 <= packet[payload_start] <= 57:
                        packet[payload_start] = 49 if packet[payload_start] == 57 else 57
                        self.modified += 1
            output.extend(packet)
        return bytes(output)


class MqttProxyHandler(socketserver.BaseRequestHandler):
    """Reenvía una conexión y transforma sus PUBLISH cliente → broker."""

    def handle(self):
        owner = self.server.owner
        transformer = PublishTransformer()
        upstream = None
        try:
            upstream = socket.create_connection((owner.broker, owner.broker_port), 10)
            upstream.settimeout(None)
            with owner._lock:
                owner._sockets.update((self.request, upstream))
            while True:
                readable, _, _ = select.select((self.request, upstream), (), (), 1)
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = upstream if source is self.request else self.request
                    if source is self.request:
                        data = transformer.feed(data)
                    if data:
                        destination.sendall(data)
        except (OSError, ValueError) as exc:
            with owner._lock:
                if not owner._closing:
                    owner.errors.append(str(exc))
        finally:
            with owner._lock:
                owner.modified += transformer.modified
                owner._sockets.discard(self.request)
                owner._sockets.discard(upstream)
            if upstream is not None:
                upstream.close()


class MqttProxyServer(socketserver.ThreadingTCPServer):
    """Servidor local con acceso explícito al estado del proxy."""

    daemon_threads = False
    allow_reuse_address = True

    def __init__(self, address, owner):
        self.owner = owner
        super().__init__(address, MqttProxyHandler)


class MqttTamperingProxy:
    def __init__(self, broker, port):
        self.broker, self.broker_port = broker, port
        self.modified = 0
        self.errors = []
        self._lock = Lock()
        self._sockets = set()
        self._closing = False

        self.server = MqttProxyServer(('127.0.0.1', 0), self)
        self.port = self.server.server_address[1]
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self._closing = True
        self.server.shutdown()
        with self._lock:
            sockets = list(self._sockets)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.server.server_close()
        self.thread.join()
