"""Pytest configuration for the MVP2 repository."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "guest: requires the disposable guest; never runs on the host or in CI",
    )
