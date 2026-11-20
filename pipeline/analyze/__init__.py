"""Deterministic ELF analysis for the AI audit gate (G2).

This package turns the frozen fixture into a source-free ``DisassemblyViewV1``
and a ``FindingV1``. It reads only the binary; it never opens the build
directory or the C source, and the serialized view carries no source path,
DWARF line table or source text.
"""

from .finding import build_finding
from .view import build_disassembly_view

__all__ = ["build_disassembly_view", "build_finding"]
