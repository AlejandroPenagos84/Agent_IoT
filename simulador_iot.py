"""
Simulador de tráfico IoT/MQTT real.

Publica en un broker Mosquitto (1883 en claro o 8883 TLS) tráfico normal de
dispositivos y, opcionalmente, inyecta ataques. La detección la realiza el
agente por separado, suscrito al broker.

Ataques disponibles:
    dos        -> flood de publicaciones a alta frecuencia
    mitm       -> payloads aleatorios de alta entropía / topic no autorizado
    intrusion  -> CONNECT anónimo (sin username) + publicaciones a $SYS/#
    todos      -> alterna los tres
"""

from __future__ import annotations

import argparse
import random
import string
import sys
import time


class IoTDevice:
    def __init__(self, device_id, topic, payloads, interval, qos=0):
        self.id = device_id
        self.topic = topic
        self.payloads = payloads
        self.interval = interval
        self.qos = qos
        self.next_time = random.uniform(0.0, interval)

    def next_payload(self):
        return str(random.choice(self.payloads))


def build_devices():
    return [
        IoTDevice('temp_salon', 'home/salon/temperatura',
                  ['21.3', '21.5', '21.8', '22.0', '22.4'], 2.0),
        IoTDevice('hum_salon', 'home/salon/humedad',
                  ['44', '45', '46', '47', '48'], 2.5),
        IoTDevice('motion_hall', 'home/pasillo/movimiento',
                  ['ON', 'OFF'], 1.5),
        IoTDevice('luz_salon', 'home/salon/luz',
                  ['ON', 'OFF'], 3.0),
        IoTDevice('cerradura', 'home/puerta/estado',
                  ['CERRADA', 'ABIERTA'], 4.0),
    ]


class DryPublisher:
    def __init__(self, client_id):
        self.client_id = client_id

    def publish(self, topic, payload, qos=0):
        return 0

    def stop(self):
        pass


class MqttPublisher:
    def __init__(self, client_id, host, port, username=None, password=None,
                 tls=None):
        from mqtt_utils import make_client

        self.client_id = client_id
        self._client = make_client(client_id, username=username,
                                   password=password, tls=tls)
        self._client.connect(host, port, 60)
        self._client.loop_start()

    def publish(self, topic, payload, qos=0):
        return self._client.publish(topic, payload, qos=qos).rc

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()


class Simulator:
    def __init__(self, args):
        self.args = args
        self.tls = self._build_tls()
        self.devices = build_devices()
        self._publishers: dict[str, object] = {}
        self.t = 0.0
        self.emitted = 0

    def _build_tls(self):
        if not (self.args.tls or self.args.port == 8883):
            return None
        return {'ca_certs': self.args.ca_certs}

    def publisher(self, client_id, anonymous=False):
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
            publisher = MqttPublisher(client_id, self.args.broker,
                                      self.args.port, username=username,
                                      password=self.args.password, tls=self.tls)
        self._publishers[client_id] = publisher
        return publisher

    def _log(self, client_id, topic, payload, origen):
        if self.args.verbose or self.args.dry_run:
            print(f"[t={self.t:7.2f}] {origen:7s} | {client_id:16s} "
                  f"-> {topic} | {payload!r}")

    def normal_tick(self):
        for device in self.devices:
            if self.t >= device.next_time:
                device.next_time = (self.t + device.interval
                                    + random.uniform(-0.2, 0.2))
                payload = device.next_payload()
                self.publisher(device.id).publish(device.topic, payload,
                                                  device.qos)
                self._log(device.id, device.topic, payload, 'normal')
                self.emitted += 1

    def _attack_packet(self, tipo):
        if tipo == 'dos':
            payload = random.choice(['ON', 'OFF'])
            self.publisher('atacante_flood').publish('home/salon/luz', payload)
            self._log('atacante_flood', 'home/salon/luz', payload, 'ataque')
        elif tipo == 'mitm':
            payload = ''.join(random.choices(string.ascii_letters + string.digits,
                                             k=random.randint(40, 120)))
            self.publisher('atacante_mitm').publish('admin/data', payload)
            self._log('atacante_mitm', 'admin/data', payload, 'ataque')
        elif tipo == 'intrusion':
            self.publisher('atacante_intr', anonymous=True).publish('cmd/system', '')
            self._log('atacante_intr', 'cmd/system', '', 'ataque')

    def attack_burst(self, tipo):
        burst = random.randint(15, 30)
        print(f"    >>> Inyectando ráfaga '{tipo}' ({burst} paquetes) <<<")
        for _ in range(burst):
            self._attack_packet(tipo)
            self.emitted += 1
            self.t += 0.02
            if self.emitted >= self.args.paquetes:
                break

    def run(self):
        next_attack = (0.1 if self.args.force_attack
                       else random.uniform(3.0, 6.0))
        print(f"\nSimulando {self.args.paquetes} paquetes "
              f"(broker={self.args.broker}:{self.args.port}, "
              f"ataque={self.args.ataque}). Ctrl+C para detener.\n")
        try:
            while self.emitted < self.args.paquetes:
                self.t += 0.1
                self.normal_tick()
                if self.args.ataque != 'none' and self.t >= next_attack:
                    tipo = (random.choice(['dos', 'mitm', 'intrusion'])
                            if self.args.ataque == 'todos' else self.args.ataque)
                    self.attack_burst(tipo)
                    next_attack = self.t + random.uniform(10.0, 20.0)
                    if self.args.debug:
                        print(f"[debug] next_attack = {next_attack:.2f}")
                time.sleep(self.args.intervalo)
        except KeyboardInterrupt:
            print("\nSimulación detenida por el usuario.")
        finally:
            self.stop()
        print(f"\nFinalizado: {self.emitted} paquetes emitidos.")

    def stop(self):
        for publisher in self._publishers.values():
            publisher.stop()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Simulador de tráfico IoT/MQTT')
    ap.add_argument('--broker', default='localhost', help='Host del broker MQTT')
    ap.add_argument('--port', type=int, default=1883, help='Puerto del broker')
    ap.add_argument('--tls', action='store_true', help='Conectar por TLS (8883)')
    ap.add_argument('--ca-certs', dest='ca_certs', default='/mosquitto/certs/ca.crt')
    ap.add_argument('--paquetes', type=int, default=60, help='Nº de paquetes')
    ap.add_argument('--ataque', default='none',
                    choices=['none', 'dos', 'mitm', 'intrusion', 'todos'])
    ap.add_argument('--intervalo', type=float, default=0.5,
                    help='Pausa entre iteraciones (segundos)')
    ap.add_argument('--usuario', default='iot', help='Usuario de dispositivos normales')
    ap.add_argument('--usuario-ataque', dest='usuario_ataque', default='atacante')
    ap.add_argument('--password', default=None)
    ap.add_argument('--force-attack', action='store_true',
                    help='Primer ataque inmediato')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--debug', action='store_true')
    ap.add_argument('--dry-run', dest='dry_run', action='store_true',
                    help='No conecta al broker; solo imprime lo que publicaría')
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    Simulator(args).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
