"""Claves con las que se agrupan los frames de una misma conexión o dirección."""

from __future__ import annotations

from .model import FrameContext


def connection_key(context: FrameContext) -> tuple:
    """Una conexión TCP (ambos sentidos), aislada por tenant, broker y sensor.

    Los endpoints van ordenados, así ida y vuelta comparten la clave. La usan la
    evidencia y el cooldown de alertas.
    """
    endpoints = tuple(
        sorted(((str(context.ip), context.srcport), (str(context.dst_ip), context.dstport)))
    )
    identity = (context.tenant_id, context.broker_id, context.sensor_id)
    return identity, context.stream_id, endpoints


def direction_key(context: FrameContext) -> tuple | None:
    """Un sentido de una conexión, o ``None`` si faltan datos de los endpoints.

    Las respuestas del broker a clientes distintos nunca comparten clave solo
    porque su puerto origen sea 1883, y ``tcp.stream`` separa conexiones
    sucesivas que reutilizan puertos.
    """
    if not context.ip or not context.dst_ip or not context.srcport or not context.dstport:
        return None
    return (
        context.tenant_id,
        context.broker_id,
        context.sensor_id,
        context.stream_id,
        context.ip,
        context.srcport,
        context.dst_ip,
        context.dstport,
    )
