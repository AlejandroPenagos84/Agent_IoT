"""Command-line arguments and entry point for the simulator."""

from __future__ import annotations

import argparse
import math

from .simulator import Simulator


def parse_args(argv=None):
    """Parse simulator options."""
    ap = argparse.ArgumentParser(description='Simulador de tráfico IoT/MQTT')
    ap.add_argument('--broker', default='localhost', help='Host del broker MQTT')
    ap.add_argument('--port', type=int, default=1883, help='Puerto del broker')
    ap.add_argument('--tls', action='store_true', help='Conectar por TLS (8883)')
    ap.add_argument('--ca-certs', dest='ca_certs', default='/mosquitto/certs/ca.crt')
    ap.add_argument('--paquetes', type=int, default=500, help='Máximo de publicaciones MQTT')
    ap.add_argument('--ataque', default='none',
                    choices=['none', 'dos'],
                    help='Escenario: tráfico normal o ráfagas DoS')
    ap.add_argument('--intervalo', type=float, default=0.5,
                    help='Pausa entre iteraciones (segundos)')
    ap.add_argument('--usuario', default='iot', help='Usuario de dispositivos normales')
    ap.add_argument('--usuario-ataque', dest='usuario_ataque', default='atacante')
    ap.add_argument('--password', default=None)
    ap.add_argument('--force-attack', action='store_true',
                    help='Primer ataque inmediato')
    ap.add_argument('--burst-size', type=int, default=100,
                    help='Publicaciones por ráfaga')
    ap.add_argument('--dos-rate', type=float, default=100,
                    help='Publicaciones/segundo durante DoS')
    ap.add_argument('--attack-gap', type=float, default=5,
                    help='Segundos entre ráfagas')
    ap.add_argument('--seed', type=int, default=None,
                    help='Semilla para reproducir payloads y horarios')
    ap.add_argument('--dos-clients', type=int, default=5)
    ap.add_argument('--dos-payload-size', type=int, default=100)
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--debug', action='store_true')
    ap.add_argument('--dry-run', dest='dry_run', action='store_true',
                    help='No conecta al broker; solo imprime lo que publicaría')
    args = ap.parse_args(argv)
    for name in ('paquetes', 'burst_size', 'dos_rate', 'intervalo',
                 'dos_clients', 'dos_payload_size'):
        if not math.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            ap.error(f'--{name.replace("_", "-")} debe ser mayor que cero')
    if not math.isfinite(args.attack_gap) or args.attack_gap < 0:
        ap.error('--attack-gap no puede ser negativo')
    return args


def main(argv=None):
    """Parse options, run the simulation, and return a process status."""
    args = parse_args(argv)
    Simulator(args).run()
    return 0
