"""Messages used by the DoS scenario; this module does not create features."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class AttackPacket:
    """Immutable message description consumed by the simulator."""
    client_id: str
    topic: str
    payload: str
    qos: int = 0


def build_attack_packet(kind: str, index=0, dos_clients=5,
                        payload_size=100) -> AttackPacket:
    """Create one packet for the persistent DoS scenario (clientes reutilizados)."""
    if kind == "dos":
        client = f'atacante_flood_{index % dos_clients}'
        payload = ''.join(random.choices('0123456789abcdefABCDEF', k=payload_size))
        return AttackPacket(client, f'mqtt-malaria/{client}/data/{index}', payload)
    raise ValueError(f"Ataque desconocido: {kind!r}")


def build_flood_packets(burst: int, client_index: int, messages: int,
                        payload_size=100) -> list[AttackPacket]:
    """Mensajes de un cliente nuevo del flood de conexiones (estilo mqtt-malaria).

    Cada cliente tiene un client_id único por ráfaga, así que abre una conexión TCP
    nueva. Los topics siguen el formato de `DoS.csv`:
    ``mqtt-malaria/<cliente>/data/<n>/<total>``.
    """
    client = f'atacante_flood_{burst}_{client_index}'
    return [AttackPacket(client, f'mqtt-malaria/{client}/data/{n}/{messages}',
                         ''.join(random.choices('0123456789abcdefABCDEF', k=payload_size)))
            for n in range(messages)]
