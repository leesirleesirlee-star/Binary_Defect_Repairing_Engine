"""Canonical JSON, hashing and status primitives for the deterministic verifier.

Every evidence hash and the reproducible ``verdict_sha256`` are computed from
canonical JSON (sorted keys, compact separators, UTF-8) so that two runs on the
same inputs cannot disagree.  The verdict vocabulary is fixed by ``VerdictV1``;
this module contains no check logic.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

PASS = "pass"
FAIL = "fail"
NOT_RUN = "not_run"

VERIFIED = "verified_against_stated_criteria"
VERDICT_VOCABULARY = frozenset(
    {
        "verified_against_stated_criteria",
        "rejected",
        "unverified",
        "unsupported",
        "error",
        "not_run",
    }
)

#: Ordered criterion catalogue: ``(id, required)``.  V0-V4 are required; V5 is
#: optional in MVP2 (spec section 8) and can never turn a non-pass into a pass.
CRITERIA: tuple[tuple[str, bool], ...] = (
    ("V0-identity", True),
    ("V1-structure", True),
    ("V2-valid-behaviour", True),
    ("V3-invalid-response", True),
    ("V4-boundary", True),
    ("V5-reapply", False),
)

SCOPE_LIMITATION = (
    "verified_against_stated_criteria is scoped to the frozen ContractV1 and "
    "CaseSetV1 of fixture stack-overflow-01; it is not a proof of whole-program "
    "correctness or security."
)
OPTIONAL_LIMITATION = (
    "V5 re-apply reproducibility is optional for MVP2 and is reported next to the "
    "required V0-V4 checks; it is not part of the success rule."
)
STATIC_LIMITATION = (
    "V4 static evidence uses bounded byte-pattern matching over the declared cave "
    "code, not a full disassembly; a guard that cannot be recognised is not_run, "
    "never a pass."
)


def sha256_hex(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    """Serialize ``value`` as deterministic compact UTF-8 JSON bytes."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    """Return the SHA-256 of the canonical JSON form of ``value``."""
    return sha256_hex(canonical_bytes(value))


def evidence_row(
    criterion_id: str,
    required: bool,
    status: str,
    evidence: Any | None = None,
) -> dict[str, Any]:
    """Build one ``VerdictV1.criteria`` row; ``not_run`` rows carry no hash."""
    if status == NOT_RUN:
        evidence = None
    return {
        "id": criterion_id,
        "required": required,
        "status": status,
        "evidence_sha256": None if evidence is None else digest(evidence),
    }


def aggregate(statuses: list[str]) -> str:
    """Combine sub-check statuses: any fail wins, then not_run, else pass."""
    if not statuses:
        return NOT_RUN
    if FAIL in statuses:
        return FAIL
    if NOT_RUN in statuses:
        return NOT_RUN
    return PASS


def utc_now() -> str:
    """Return the current UTC time as an RFC 3339 timestamp with ``Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hex_int(value: Any, label: str) -> int:
    """Parse a manifest ``0x...`` address or raise a labelled ValueError."""
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a hex string")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{label} is not a hex integer: {value!r}") from exc


def hex_bytes(value: Any, label: str) -> bytes:
    """Parse a manifest hex-byte string or raise a labelled ValueError."""
    if not isinstance(value, str) or len(value) % 2 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{label} must be lowercase hex bytes")
    return bytes.fromhex(value)


def argv_sha256(argv: list[str]) -> str:
    """Hash a case argv exactly as ``guest/run_cases.py`` does."""
    encoded = json.dumps(argv, separators=(",", ":")).encode("utf-8")
    return sha256_hex(encoded)


def decode_b64(value: Any) -> bytes:
    """Decode an observation base64 field, rejecting malformed payloads."""
    if not isinstance(value, str):
        raise ValueError("base64 field must be a string")
    return base64.b64decode(value, validate=True)


def verdict_sha256(verdict: dict[str, Any]) -> str:
    """Return the reproducible verdict hash (``produced_at`` excluded)."""
    payload = {key: value for key, value in verdict.items() if key != "produced_at"}
    return digest(payload)
