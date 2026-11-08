"""Regla STRUCTURAL_NULL: alineación con un tipo de paquete y separación DoS."""

from .analysis import packet_type_separation, structural_null_alignment
from .plots import plot_packet_separation, plot_structural_presence

__all__ = [
    'structural_null_alignment', 'packet_type_separation',
    'plot_structural_presence', 'plot_packet_separation',
]
