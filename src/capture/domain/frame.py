"""Frame TCP validado a partir del registro crudo de tshark.

IP, puertos y ``frame.time_epoch`` solo son claves y reloj, nunca features.
"""

from __future__ import annotations

import math
from typing import NamedTuple

MQTT_PORTS = (1883, 8883)
CONNECT_TYPE = 1

Endpoint = tuple[str, int]


def _number(value, default=None):
    """Convierte a float finito; devuelve ``default`` si no se puede."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    if not math.isfinite(result):
        return default

    return result


def _port(value):
    """Convierte a puerto entero; devuelve ``None`` si no es un entero válido."""
    result = _number(value)

    if result is None or not result.is_integer():
        return None

    return int(result)


class TcpFrame(NamedTuple):
    time: float
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    length: float
    time_delta: float
    is_connect: bool

    @classmethod
    def from_record(cls, record: dict) -> TcpFrame | None:
        """Frame del registro, o ``None`` si falta IP/puerto/tiempo o no es MQTT.

        El modelo se entrenó solo con frames con puerto 1883/8883 en origen o
        destino (``training_scope = mqtt_ports``); el resto se descarta aquí.
        """
        now = _number(record.get('frame.time_epoch'))

        src_ip = record.get('ip.src')
        dst_ip = record.get('ip.dst')

        src_port = _port(record.get('tcp.srcport'))
        dst_port = _port(record.get('tcp.dstport'))

        if now is None:
            return None
        if not src_ip or not dst_ip:
            return None
        if src_port is None or dst_port is None:
            return None
        if src_port not in MQTT_PORTS and dst_port not in MQTT_PORTS:
            return None

        length = _number(record.get('frame.len'), 0.0)
        time_delta = max(_number(record.get('frame.time_delta'), 0.0), 0.0)
        is_connect = _number(record.get('mqtt.msgtype')) == CONNECT_TYPE

        return cls(
            time=now,
            src_ip=str(src_ip),
            src_port=src_port,
            dst_ip=str(dst_ip),
            dst_port=dst_port,
            length=length,
            time_delta=time_delta,
            is_connect=is_connect,
        )

    @property
    def to_broker(self) -> bool:
        return self.dst_port in MQTT_PORTS

    @property
    def from_broker(self) -> bool:
        return self.src_port in MQTT_PORTS

    @property
    def endpoints(self) -> tuple[Endpoint, Endpoint]:
        """Par de endpoints no dirigido: identifica la conexión en ambos sentidos."""
        source = (self.src_ip, self.src_port)
        destination = (self.dst_ip, self.dst_port)

        return tuple(sorted((source, destination)))

    @property
    def direction(self) -> tuple[str, int, str, int]:
        return (self.src_ip, self.src_port, self.dst_ip, self.dst_port)
