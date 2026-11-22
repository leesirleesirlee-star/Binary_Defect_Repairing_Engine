"""Read-only snapshot of the frozen G1 fixture used by the S2 console surface.

This module only reads persisted JSON. It does not import any pipeline module
and never computes a verdict, score or success label.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FIXTURE_ID = "stack-overflow-01"
FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / FIXTURE_ID
CONTRACT_REVISION = 1
_APPROVED: dict[str, Any] | None = None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding_digest() -> str:
    """Content binding approved for the frozen task (three digests + revision)."""
    contract = _read_json(FIXTURE_ROOT / "contract.json")
    manifest = _read_json(FIXTURE_ROOT / "fixture-manifest.json")
    cases = _read_json(FIXTURE_ROOT / "cases" / "cases.json")
    payload = {
        "revision": CONTRACT_REVISION,
        "contract_sha256": _sha256(FIXTURE_ROOT / "contract.json"),
        "corpus_sha256": _sha256(FIXTURE_ROOT / "cases" / "cases.json"),
        "binary_sha256": manifest["binary"]["sha256"],
    }
    assert contract["binary_sha256"] == payload["binary_sha256"]
    assert cases["fixture_id"] == FIXTURE_ID
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _approved_state() -> dict[str, Any] | None:
    return dict(_APPROVED) if _APPROVED else None


def snapshot() -> dict[str, Any]:
    """The persisted fixture, contract and corpus as review-only console data."""
    contract = _read_json(FIXTURE_ROOT / "contract.json")
    manifest = _read_json(FIXTURE_ROOT / "fixture-manifest.json")
    cases = _read_json(FIXTURE_ROOT / "cases" / "cases.json")
    poc_path = FIXTURE_ROOT / "cases" / "poc.txt"
    counts = {"valid": 0, "invalid": 0, "poc": 0}
    public_cases = []
    for case in cases["cases"]:
        kind = case["kind"]
        counts[kind] = counts.get(kind, 0) + 1
        public_cases.append({
            "id": case["id"],
            "kind": kind,
            "argv": list(case.get("argv") or []),
            "stdin": case.get("stdin", ""),
            "expected_original": case.get("expected_original"),
            "expected_candidate": case.get("expected_candidate"),
        })
    approved = _approved_state()
    return {
        "fixture_id": FIXTURE_ID,
        "frozen": True,
        "binary": {
            "path": manifest["binary"]["path"],
            "sha256": manifest["binary"]["sha256"],
            "size": manifest["binary"]["size"],
        },
        "elf": manifest["elf"],
        "reserved_range": manifest["reserved_range"],
        "defect": contract["diagnostic_hypothesis"]["statement"],
        "target_function": contract["target_function"],
        "contract": contract,
        "contract_revision": CONTRACT_REVISION,
        "contract_sha256": _sha256(FIXTURE_ROOT / "contract.json"),
        "hashes": {
            "contract_sha256": _sha256(FIXTURE_ROOT / "contract.json"),
            "corpus_sha256": _sha256(FIXTURE_ROOT / "cases" / "cases.json"),
            "binary_sha256": manifest["binary"]["sha256"],
        },
        "corpus": {
            "fixture_id": FIXTURE_ID,
            "counts": counts,
            "total": len(public_cases),
            "cases": public_cases,
            "cases_sha256": _sha256(FIXTURE_ROOT / "cases" / "cases.json"),
            "poc": {
                "path": "cases/poc.txt",
                "sha256": _sha256(poc_path),
                "text": poc_path.read_text(encoding="utf-8"),
            },
        },
        "review_binding_digest": binding_digest(),
        "approval": approved or {"approved": False, "binding_digest": binding_digest()},
    }


def approve(
    expected_binding_digest: str | None = None,
    reviewer_label: str = "M2",
) -> dict[str, Any]:
    """Approve the frozen binding, rejecting a stale digest."""
    global _APPROVED
    current = binding_digest()
    if expected_binding_digest is not None and expected_binding_digest != current:
        raise ValueError("stale_approval")
    _APPROVED = {
        "approved": True,
        "approved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "reviewer_label": reviewer_label,
        "binding_digest": current,
        "contract_sha256": _sha256(FIXTURE_ROOT / "contract.json"),
        "corpus_sha256": _sha256(FIXTURE_ROOT / "cases" / "cases.json"),
        "binary_sha256": snapshot()["binary"]["sha256"],
    }
    return dict(_APPROVED)


def reset_approval() -> None:
    """Test helper: clear the in-memory S2 approval state."""
    global _APPROVED
    _APPROVED = None
