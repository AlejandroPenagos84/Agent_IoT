"""Messages used by attack scenarios; this module does not create features."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class AttackPacket:
    """Immutable message description consumed by the simulator."""
    client_id: str
    topic: str
    payload: str
    anonymous: bool = False
    qos: int = 0


def build_attack_packet(kind: str, index=0, dos_clients=5, payload_size=100,
                        discovered=None) -> AttackPacket:
    """Create one packet for a supported attack scenario."""
    if kind == "dos":
        client = f'atacante_flood_{index % dos_clients}'
        payload = ''.join(random.choices('0123456789abcdefABCDEF', k=payload_size))
        return AttackPacket(client, f'mqtt-malaria/{client}/data/{index}', payload)
    if kind == "mitm":
        return AttackPacket('sonar_mitm', 'distance/ultrasonic1', '100', qos=1)
    if kind == "intrusion":
        if not discovered:
            raise ValueError('Intrusion requiere descubrir topics con SUBSCRIBE #')
        topic = sorted(discovered)[index % len(discovered)]
        payload = '999' if topic.startswith('distance/') else '1'
        return AttackPacket('atacante_intr', topic, payload, anonymous=True, qos=1)
    raise ValueError(f"Ataque desconocido: {kind!r}")
