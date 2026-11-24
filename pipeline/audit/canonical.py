"""Canonical plan hash, independent of JSON formatting.

Plan selection needs a hash that does not change when the same plan is re-serialised
with different indentation or key order. ``canonical_plan_hash`` hashes the sorted-key,
compact JSON, so a plan picked in the GUI and the same plan stored on disk hash alike.
"""

from __future__ import annotations

import hashlib
import json


def canonical_plan_hash(plan: dict) -> str:
    """Return sha256 over the sorted-key, compact JSON of ``plan``."""
    compact = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()
