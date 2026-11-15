"""Estado en memoria que usan los casos de uso (no son reglas de negocio)."""

from .evidence_buffer import EvidenceBuffer
from .sliding_windows import SlidingWindows

__all__ = ['EvidenceBuffer', 'SlidingWindows']
