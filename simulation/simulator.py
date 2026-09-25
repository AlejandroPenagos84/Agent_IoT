"""Scheduling for normal traffic and attack bursts."""

from __future__ import annotations

import random
import time

from .attacks import build_attack_packet
from .devices import build_devices
from .publishers import DryPublisher, MqttPublisher, Publisher


class Simulator:
    """Run a bounded simulation using injected publisher implementations."""

    def __init__(self, args):
        """Initialize runtime settings, devices, publisher cache, and counters."""
        self.args = args
        if args.seed is not None:
            random.seed(args.seed)
        self.tls = self._build_tls()
        self.devices = build_devices()
        self._publishers: dict[str, Publisher] = {}
        self.t = 0.0
        self.emitted = 0
        self.counts = dict.fromkeys(('normal', 'dos'), 0)
        self._started = None

    def _refresh_time(self):
        if not self.args.dry_run:
            self.t = time.monotonic() - self._started

    def _wait(self, seconds):
        if self.args.dry_run:
            self.t += seconds
        else:
            time.sleep(max(0, seconds))
            self._refresh_time()

    def _publish(self, client_id, topic, payload, kind, qos=0):
        rc = self.publisher(client_id).publish(topic, payload, qos)
        if rc != 0:
            raise RuntimeError(
                f'Publicación fallida: client={client_id}, topic={topic}, rc={rc}'
            )
        self._refresh_time()
        self._log(client_id, topic, payload, kind)
        self.emitted += 1
        self.counts[kind] += 1

    def _build_tls(self):
        """Return paho TLS settings when TLS is requested."""
        if not (self.args.tls or self.args.port == 8883):
            return None
        return {'ca_certs': self.args.ca_certs}

    def publisher(self, client_id):
        """Get or create the cached publisher for a simulated client."""
        if client_id in self._publishers:
            return self._publishers[client_id]
        if self.args.dry_run:
            publisher = DryPublisher(client_id)
        else:
            if client_id.startswith('atacante'):
                username = self.args.usuario_ataque
            else:
                username = self.args.usuario
            host, port = self.args.broker, self.args.port
            publisher = MqttPublisher(
                client_id,
                host,
                port,
                username=username,
                password=self.args.password,
                tls=self.tls,
            )
        self._publishers[client_id] = publisher
        return publisher

    def _log(self, client_id, topic, payload, origen):
        """Print one message when verbose or dry-run output is enabled."""
        if self.args.verbose or self.args.dry_run:
            print(f"[t={self.t:7.2f}] {origen:7s} | {client_id:16s} "
                  f"-> {topic} | {payload!r}")

    def normal_tick(self):
        """Publish devices whose scheduled timestamp has elapsed."""
        for device in self.devices:
            if self.emitted >= self.args.paquetes:
                break
            if self.t >= device.next_time:
                device.next_time = (
                    self.t + device.interval + random.uniform(-0.2, 0.2)
                )
                payload = device.next_payload()
                self._publish(
                    device.id, device.topic, payload, 'normal', device.qos
                )

    def attack_burst(self):
        """Publish a bounded DoS burst paced by elapsed wall-clock time."""
        tipo = 'dos'
        burst = min(self.args.burst_size, self.args.paquetes - self.emitted)
        rate = self.args.dos_rate

        def packet_at(index):
            return build_attack_packet(
                tipo,
                index,
                self.args.dos_clients,
                self.args.dos_payload_size,
            )

        # Conectar antes de medir; repartir la carga entre clientes DoS reales.
        for index in range(min(burst, self.args.dos_clients)):
            packet = packet_at(index)
            self.publisher(packet.client_id)
        self._refresh_time()
        started = self.t
        print(
            f"    >>> Ráfaga '{tipo}': {burst} publicaciones, objetivo={rate:g}/s <<<"
        )
        for index in range(burst):
            self._wait(max(0, started + index / rate - self.t))
            packet = packet_at(index)
            self._publish(
                packet.client_id,
                packet.topic,
                packet.payload,
                tipo,
                qos=packet.qos,
            )
        elapsed = self.t - started
        measured = (burst - 1) / elapsed if burst > 1 and elapsed > 0 else 0
        print(
            f"    >>> Fin '{tipo}': {elapsed:.3f}s, ritmo={measured:.1f}/s <<<"
        )

    def run(self):
        """Run until the requested message count or user interruption."""
        self._started = time.monotonic()
        next_attack = (
            0.0 if self.args.force_attack else random.uniform(3.0, 6.0)
        )
        print(
            f"\nSimulando {self.args.paquetes} publicaciones MQTT "
            f"(broker={self.args.broker}:{self.args.port}, "
            f"ataque={self.args.ataque}). Ctrl+C para detener.\n"
        )
        try:
            while self.emitted < self.args.paquetes:
                self._refresh_time()
                if self.args.ataque != 'none' and self.t >= next_attack:
                    self.attack_burst()
                    next_attack = self.t + self.args.attack_gap
                    if self.args.debug:
                        print(f"[debug] next_attack = {next_attack:.2f}")
                self.normal_tick()
                if self.emitted < self.args.paquetes:
                    self._wait(self.args.intervalo)
        except KeyboardInterrupt:
            print("\nSimulación detenida por el usuario.")
        finally:
            self.stop()
        print(f"\nFinalizado: {self.emitted} publicaciones completadas; {self.counts}")

    def stop(self):
        """Stop every cached publisher."""
        errors = []
        for publisher in self._publishers.values():
            try:
                publisher.stop()
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError(
                'Error al completar publicaciones: ' + '; '.join(errors)
            )
