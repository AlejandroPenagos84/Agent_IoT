"""Comando de tshark para la captura."""

from __future__ import annotations

from collections.abc import Sequence

from capture.infrastructure.tshark.schema import CAPTURE_FIELDS


def build_display_filter(base: str, exclude_topic: str | None) -> str:
    """Agrega al display filter una exclusión segura del topic."""
    if not exclude_topic:
        return base
    # `!(field == value)` también deja pasar los registros sin ese campo.
    exclusion = f'!(mqtt.topic == "{exclude_topic}")'
    return f'({base}) && {exclusion}' if base else exclusion


def build_command(
    iface: str,
    display_filter: str = '',
    exclude_topic: str | None = None,
    fields: Sequence[str] = CAPTURE_FIELDS,
) -> list[str]:
    """Comando ``tshark -T fields`` con salida por línea (``-l``)."""
    cmd = ['tshark', '-l', '-n', '-i', iface, '-T', 'fields', '-E', 'occurrence=f', '-E', 'quote=d']
    full_filter = build_display_filter(display_filter, exclude_topic)
    if full_filter:
        cmd += ['-Y', full_filter]
    for field in fields:
        cmd += ['-e', field]
    return cmd
