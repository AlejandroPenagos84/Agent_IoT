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
    """Create one packet for the DoS attack scenario."""
    if kind == "dos":
        client = f'atacante_flood_{index % dos_clients}'
        payload = ''.join(random.choices('0123456789abcdefABCDEF', k=payload_size))
        return AttackPacket(client, f'mqtt-malaria/{client}/data/{index}', payload)
    raise ValueError(f"Ataque desconocido: {kind!r}")
