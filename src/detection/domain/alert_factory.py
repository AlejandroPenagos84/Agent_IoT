"""Construcción de la alerta a partir del frame que la disparó."""

from __future__ import annotations

import uuid
from collections.abc import Collection

from .model import ALERT_KIND_CLASS, Alert, FrameContext


def client_ip(context: FrameContext, server_ports: Collection[int]) -> str | None:
    """IP del cliente: si el frame va broker -> cliente, el cliente es el destino."""
    if context.srcport in server_ports and context.dst_ip:
        return context.dst_ip
    return context.ip


def build_alert(
    label: str, context: FrameContext, *, source: str, server_ports: Collection[int] = ()
) -> Alert:
    """Alerta de clasificación con un ``alert_id`` nuevo y la identidad del sensor."""
    return Alert(
        ts=context.ts or 0.0,
        kind=ALERT_KIND_CLASS,
        label=label,
        client_id=context.client_id,
        ip=client_ip(context, server_ports),
        topic=context.topic,
        source=source,
        alert_id=str(uuid.uuid4()),
        tenant_id=context.tenant_id,
        broker_id=context.broker_id,
        sensor_id=context.sensor_id,
    )
