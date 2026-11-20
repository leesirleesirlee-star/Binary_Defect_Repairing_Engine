"""Canonical manifest hashing shared by the writer and self-check.

Local filesystem paths are evidence metadata, not repair facts.  They are
excluded from the canonical hash so the same bytes produce the same hash on a
different machine or checkout.  Optional `created_at` and the hash field itself
are also excluded.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

EXCLUDED_TOP_LEVEL = ("created_at", "manifest_sha256")


def canonical_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the manifest with environment metadata removed."""
    payload = copy.deepcopy(manifest)
    for key in EXCLUDED_TOP_LEVEL:
        payload.pop(key, None)
    original = payload.get("original")
    if isinstance(original, dict):
        original.pop("path", None)
    contract = payload.get("contract")
    if isinstance(contract, dict):
        contract.pop("path", None)
    return payload


def manifest_sha256(manifest: dict[str, Any]) -> str:
    """Hash the canonical manifest payload."""
    encoded = json.dumps(
        canonical_payload(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
