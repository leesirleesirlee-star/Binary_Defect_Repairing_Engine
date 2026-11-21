"""Three-run AI audit harness, fixed rubric and report (module: audit, gate G2)."""

from .harness import run_audit
from .report import build_report
from .rubric import CRITICAL_ERRORS, PASS_THRESHOLD, RUBRIC, TOTAL_POINTS, decide

__all__ = [
    "CRITICAL_ERRORS",
    "PASS_THRESHOLD",
    "RUBRIC",
    "TOTAL_POINTS",
    "build_report",
    "decide",
    "run_audit",
]
