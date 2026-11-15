"""Conversión de la salida ``-T fields`` de tshark a registros tipados."""

from __future__ import annotations

import csv
from collections.abc import Sequence

from capture.infrastructure.tshark.schema import CAPTURE_FIELDS, FLOAT_FIELDS, INT_FIELDS


def _coerce(field: str, value: str):
    """Convierte un campo de tshark a su tipo, o ``None`` si está vacío o es inválido."""
    if value == '':
        return None
    if field in INT_FIELDS:
        try:
            return int(value)
        except ValueError:
            return None
    if field in FLOAT_FIELDS:
        try:
            return float(value)
        except ValueError:
            return None
    return value


def record_from_fields(values: Sequence[str], fields: Sequence[str] = CAPTURE_FIELDS) -> dict:
    """Mapea los valores separados por tab al registro de la captura."""
    return {field: _coerce(field, value) for field, value in zip(fields, values, strict=False)}


def parse_line(line: str, fields: Sequence[str] = CAPTURE_FIELDS) -> dict:
    """Una línea de tshark (con ``quote=d``) a registro."""
    values = next(csv.reader([line.rstrip('\n')], delimiter='\t'))
    return record_from_fields(values, fields)
