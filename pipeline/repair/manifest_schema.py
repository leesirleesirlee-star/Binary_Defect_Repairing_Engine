"""Provisional manifest shape and forward-compatible mapping hooks.

M1 has not published the frozen ``EditManifestV1`` schema yet.  This module keeps
the current dry-run shape explicit, validates its required fields, and reserves
extension slots so the final mapping can be added without rewriting the repair
tools.

This is **not** a schema definition and must not be cited as one.  M1 owns
``schemas/``; any real schema change is an M1 PR plus ADR.
"""

from __future__ import annotations

import copy
from typing import Any

PROVISIONAL_SCHEMA = "m5-dryrun-v0"
TARGET_SCHEMA = "EditManifestV1"
TARGET_STATUS = "draft-pending-M1"

REQUIRED_FIELDS = (
    "schema_version",
    "dry_run",
    "original",
    "patch_site",
    "cave",
    "trampoline",
    "edits",
    "invariants",
    "reversibility",
    "preview",
    "verdict",
)

# Future fields can be parked here until M1 freezes their exact names.
EXTENSION_SLOTS = (
    "fixture_contract",
    "g2_plan",
    "reserved_range",
    "source_provenance",
    "verifier_hints",
    "review",
)


class ManifestShapeError(ValueError):
    """Raised when the provisional manifest is missing a required field."""


def validate_provisional_shape(manifest: dict[str, Any]) -> None:
    """Check the fields every M5 dry-run manifest must carry.

    The check is structural only; it does not validate contract semantics.
    """
    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    if missing:
        raise ManifestShapeError(f"manifest missing required fields: {', '.join(missing)}")
    if manifest["schema_version"] != PROVISIONAL_SCHEMA:
        raise ManifestShapeError(
            f"unexpected schema_version {manifest['schema_version']!r}"
        )
    if manifest["dry_run"] is not True:
        raise ManifestShapeError("dry_run must be true")
    if not isinstance(manifest["edits"], list) or not manifest["edits"]:
        raise ManifestShapeError("edits must be a non-empty list")
    if manifest["verdict"] is not None:
        raise ManifestShapeError("M5 manifests must carry verdict=null")


def normalize_provisional(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with stable extension slots and mapping metadata.

    The copy is deterministic: repeated calls produce the same key/value shape.
    Unknown fields are preserved.
    """
    normalized = copy.deepcopy(manifest)
    extensions = normalized.setdefault("extensions", {})
    if not isinstance(extensions, dict):
        raise ManifestShapeError("extensions must be an object")
    for slot in EXTENSION_SLOTS:
        extensions.setdefault(slot, None)
    normalized["schema_mapping"] = {
        "source": PROVISIONAL_SCHEMA,
        "target": TARGET_SCHEMA,
        "status": TARGET_STATUS,
        "note": "M1 must freeze EditManifestV1 before this mapping is authoritative.",
    }
    return normalized


def to_edit_manifest_v1(manifest: dict[str, Any]) -> dict[str, Any]:
    """Map the provisional manifest to a conservative draft v1 shape.

    The mapping keeps only fields whose meaning is unambiguous.  Everything else
    stays under ``extensions`` so no information is silently dropped.
    """
    validate_provisional_shape(manifest)
    return {
        "schema_version": 1,
        "schema_kind": TARGET_SCHEMA,
        "schema_status": TARGET_STATUS,
        "dry_run": True,
        "original": manifest["original"],
        "patch_site": manifest["patch_site"],
        "cave": manifest["cave"],
        "trampoline": manifest["trampoline"],
        "edits": manifest["edits"],
        "invariants": manifest["invariants"],
        "reversibility": manifest["reversibility"],
        "preview": manifest["preview"],
        "extensions": copy.deepcopy(manifest.get("extensions", {})),
        "verdict": None,
        "verdict_note": "M5 does not write or infer verdicts; M3 owns verification.",
    }
