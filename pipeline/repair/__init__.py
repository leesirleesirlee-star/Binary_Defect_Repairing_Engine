"""M5 repair tools: ELF64 dry-run editing, cave finding and manifest writing.

The package is pure Python and has no third-party runtime dependencies.  It is
deliberately dry-run only until G2 approves a repair plan.
"""

from __future__ import annotations

__version__ = "0.1.0-dryrun"

EXIT_OK = 0
EXIT_CHECK_FAILED = 1
EXIT_ERROR = 2
