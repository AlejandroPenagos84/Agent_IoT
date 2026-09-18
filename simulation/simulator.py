"""Scheduling for normal traffic and attack bursts."""

from __future__ import annotations

import random
import time
from itertools import cycle

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
        self.scenarios = cycle(('dos', 'mitm', 'intrusion'))
        self.counts = dict.fromkeys(('normal', 'dos', 'mitm', 'intrusion'), 0)
        self._started = None
        self._proxy = None
        self._discovered = None

    def _refresh_time(self):
        if not self.args.dry_run:
            self.t = time.monotonic() - self._started

    def _wait(self, seconds):
        if self.args.dry_run:
            self.t += seconds
        else:
            time.sleep(max(0, seconds))
            self._refresh_time()

    def _publish(self, client_id, topic, payload, kind, qos=0, anonymous=False):
        rc = self.publisher(client_id, anonymous).publish(topic, payload, qos)
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

    def publisher(self, client_id, anonymous=False):
        """Get or create the cached publisher for a simulated client."""
        if client_id in self._publishers:
            return self._publishers[client_id]
        if self.args.dry_run:
            publisher = DryPublisher(client_id)
        else:
            if anonymous:
                username = None
            elif client_id.startswith('atacante'):
                username = self.args.usuario_ataque
            else:
                username = self.args.usuario
            host, port = self.args.broker, self.args.port
            if client_id == 'sonar_mitm':
                from .mqtt_proxy import MqttTamperingProxy
                if self._proxy is None:
                    self._proxy = MqttTamperingProxy(host, port)
                host, port = '127.0.0.1', self._proxy.port
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
            # Reserve enough budget for the first complete cycle of todos.
            remaining = sum(
                max(0, self.args.burst_size - self.counts[kind])
                for kind in ('dos', 'mitm', 'intrusion')
            )
            if self._discovered is None:
                remaining += len(self.devices)
            if (self.args.ataque == 'todos'
                    and self.args.paquetes - self.emitted <= remaining):
                break
            if self.t >= device.next_time:
                device.next_time = (
                    self.t + device.interval + random.uniform(-0.2, 0.2)
                )
                payload = device.next_payload()
                self._publish(
                    device.id, device.topic, payload, 'normal', device.qos
                )

    def attack_burst(self, tipo):
        """Publish a bounded burst paced by elapsed wall-clock time."""
        if tipo == 'intrusion' and self._discovered is None:
            intruder = self.publisher('atacante_intr', anonymous=True)
            intruder.subscribe('#')
            print(
                '    >>> Intrusion: SUBSCRIBE #, observación y publicación falsa <<<'
            )
            if self.args.paquetes - self.emitted < len(self.devices) + 1:
                raise RuntimeError(
                    'Presupuesto insuficiente para discovery y publicación intrusion'
                )
            for device in self.devices:
                self._publish(
                    device.id,
                    device.topic,
                    device.next_payload(),
                    'normal',
                    device.qos,
                )
            self._wait(self.args.discovery_seconds)
            observed = (
                dict.fromkeys((device.topic for device in self.devices), '')
                if self.args.dry_run
                else intruder.observed_topics()
            )
            self._discovered = {
                topic: payload
                for topic, payload in observed.items()
                if topic != 'alertas/deteccion'
                and not topic.startswith('$')
                and '#' not in topic
                and '+' not in topic
            }
            if not self._discovered:
                raise RuntimeError(
                    'El intruso no recibió topics: revisar broker/ACL/discovery-seconds'
                )
            print(f'    >>> Topics descubiertos: {sorted(self._discovered)} <<<')
        burst = min(self.args.burst_size, self.args.paquetes - self.emitted)
        rate = self.args.dos_rate if tipo == 'dos' else self.args.attack_rate

        def packet_at(index):
            return build_attack_packet(
                tipo,
                index,
                self.args.dos_clients,
                self.args.dos_payload_size,
                self._discovered,
            )

        # Conectar antes de medir; repartir la carga entre clientes DoS reales.
        for index in range(
            min(burst, self.args.dos_clients) if tipo == 'dos' else 1
        ):
            packet = packet_at(index)
            self.publisher(packet.client_id, packet.anonymous)
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
                anonymous=packet.anonymous,
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
        if self.args.ataque in ('mitm', 'intrusion', 'todos'):
            print('Escenarios MQTT_UAD: DoS multicliente; MitM con proxy MQTT que '
                  'modifica lecturas en tránsito; intrusion con SUBSCRIBE # y '
                  'publicación falsa en topics observados. El proxy requiere '
                  'conexión explícita del sensor, no realiza ARP spoofing.\n')
        try:
            while self.emitted < self.args.paquetes:
                self._refresh_time()
                if self.args.ataque != 'none' and self.t >= next_attack:
                    tipo = (
                        next(self.scenarios)
                        if self.args.ataque == 'todos'
                        else self.args.ataque
                    )
                    self.attack_burst(tipo)
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
        if self._proxy is not None:
            self._proxy.stop()
            print(
                f'MitM: {self._proxy.modified} PUBLISH modificados por el proxy'
            )
            if self._proxy.errors:
                errors.extend(self._proxy.errors)
        if errors:
            raise RuntimeError(
                'Error al completar publicaciones: ' + '; '.join(errors)
            )
