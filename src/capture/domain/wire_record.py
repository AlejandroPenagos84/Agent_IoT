"""Registro que la captura envía al agente (contrato de ``wire``)."""

from __future__ import annotations

from wire.protocol import RECORD_FIELDS


def wire_record(record: dict, features: dict, identity: dict | None = None) -> dict:
    """Solo los campos seguros del contrato, la identidad y las features TCP."""
    wire = {field: record.get(field) for field in RECORD_FIELDS if field != 'tcp_features'}

    if identity:
        wire.update({key: value for key, value in identity.items() if value})
    wire['tcp_features'] = features

    return wire
