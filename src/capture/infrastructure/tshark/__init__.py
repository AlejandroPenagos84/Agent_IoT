"""Fuente de paquetes basada en tshark."""

from capture.infrastructure.tshark.command import build_command, build_display_filter
from capture.infrastructure.tshark.parser import parse_line, record_from_fields
from capture.infrastructure.tshark.schema import CAPTURE_FIELDS, RECORD_FIELDS
from capture.infrastructure.tshark.tshark_source import TsharkPacketSource

__all__ = [
    'CAPTURE_FIELDS',
    'RECORD_FIELDS',
    'TsharkPacketSource',
    'build_command',
    'build_display_filter',
    'parse_line',
    'record_from_fields',
]
