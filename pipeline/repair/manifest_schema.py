"""Manifest shape helpers and the EditManifestV1 alignment layer.

M1 owns ``schemas/``.  This module does not define a schema file; it keeps the
provisional dry-run shape and provides a standard-library-only mapper/validator
for the public ``EditManifestV1`` draft in PR #22.
"""

from __future__ import annotations

import copy
import re
from typing import Any

PROVISIONAL_SCHEMA = "m5-dryrun-v0"
TARGET_SCHEMA = "EditManifestV1"
TARGET_STATUS = "draft-pending-M1"
EDIT_MANIFEST_V1_VERSION = 1

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

V1_ALLOWED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "manifest_kind",
        "tool",
        "tool_version",
        "schema_note",
        "dry_run",
        "fixture_id",
        "plan_id",
        "original",
        "contract",
        "patch_site",
        "cave",
        "trampoline",
        "edits",
        "invariants",
        "reversibility",
        "preview",
        "limits",
        "warnings",
        "verdict",
        "verdict_note",
        "created_at",
        "manifest_sha256",
        "extensions",
    }
)
V1_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "dry_run",
    "fixture_id",
    "plan_id",
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
V1_ORIGINAL_FIELDS = ("path", "sha256", "size", "entry", "class", "machine", "type")
V1_PATCH_SITE_FIELDS = (
    "vaddr",
    "file_offset",
    "size",
    "original_bytes",
    "patch_bytes",
    "target_cave_vaddr",
)
V1_CAVE_FIELDS = ("vaddr", "file_offset", "total_size", "fill")
V1_TRAMPOLINE_FIELDS = ("entry_vaddr", "blob", "blob_sha256", "total_size")
V1_EDIT_FIELDS = (
    "name",
    "vaddr",
    "file_offset",
    "size",
    "original_bytes",
    "patch_bytes",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_BYTES = re.compile(r"^([0-9a-f]{2})*$")
_ADDRESS = re.compile(r"^0x[0-9a-f]+$")
_FIXTURE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ManifestShapeError(ValueError):
    """Raised when a manifest does not satisfy the expected shape."""


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestShapeError(f"{name} must be an object")
    return value


def _require_fields(value: dict[str, Any], fields: tuple[str, ...], name: str) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise ManifestShapeError(f"{name} missing required fields: {', '.join(missing)}")


def _require_addr(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _ADDRESS.fullmatch(value):
        raise ManifestShapeError(f"{name} must be a 0x-prefixed address")


def _require_bytes(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _HEX_BYTES.fullmatch(value):
        raise ManifestShapeError(f"{name} must be lowercase hex bytes")


def _require_size(value: Any, name: str, *, minimum: int = 1) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ManifestShapeError(f"{name} must be an integer >= {minimum}")


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


def validate_edit_manifest_v1(manifest: dict[str, Any]) -> None:
    """Validate the public EditManifestV1 shape without third-party libraries.

    This mirrors the closed top-level and nested required fields in PR #22's
    draft.  It is intentionally a shape check, not a semantic repair check.
    """
    _require_object(manifest, "manifest")
    extra = sorted(set(manifest) - V1_ALLOWED_TOP_LEVEL)
    if extra:
        raise ManifestShapeError(f"unexpected top-level fields: {', '.join(extra)}")
    _require_fields(manifest, V1_REQUIRED_TOP_LEVEL, "manifest")

    version = manifest["schema_version"]
    if isinstance(version, bool) or version != EDIT_MANIFEST_V1_VERSION:
        raise ManifestShapeError(
            f"schema_version must be integer {EDIT_MANIFEST_V1_VERSION}"
        )
    if manifest["dry_run"] is not True:
        raise ManifestShapeError("dry_run must be true")
    if not isinstance(manifest["fixture_id"], str) or not _FIXTURE_ID.fullmatch(
        manifest["fixture_id"]
    ):
        raise ManifestShapeError("fixture_id must match ^[a-z0-9][a-z0-9-]*$")
    if not isinstance(manifest["plan_id"], str) or not manifest["plan_id"]:
        raise ManifestShapeError("plan_id must be a non-empty string")
    if manifest["verdict"] is not None:
        raise ManifestShapeError("verdict must be null")

    original = _require_object(manifest["original"], "original")
    _require_fields(original, V1_ORIGINAL_FIELDS, "original")
    if not isinstance(original["path"], str):
        raise ManifestShapeError("original.path must be a string")
    if not isinstance(original["sha256"], str) or not _HEX64.fullmatch(original["sha256"]):
        raise ManifestShapeError("original.sha256 must be 64 lowercase hex chars")
    _require_size(original["size"], "original.size")
    _require_addr(original["entry"], "original.entry")
    if original["class"] != "ELF64":
        raise ManifestShapeError("original.class must be ELF64")
    if original["machine"] != "EM_X86_64":
        raise ManifestShapeError("original.machine must be EM_X86_64")
    if original["type"] != "ET_EXEC":
        raise ManifestShapeError("original.type must be ET_EXEC")

    patch_site = _require_object(manifest["patch_site"], "patch_site")
    _require_fields(patch_site, V1_PATCH_SITE_FIELDS, "patch_site")
    for field in ("vaddr", "file_offset", "target_cave_vaddr"):
        _require_addr(patch_site[field], f"patch_site.{field}")
    _require_size(patch_site["size"], "patch_site.size")
    _require_bytes(patch_site["original_bytes"], "patch_site.original_bytes")
    _require_bytes(patch_site["patch_bytes"], "patch_site.patch_bytes")

    cave = _require_object(manifest["cave"], "cave")
    _require_fields(cave, V1_CAVE_FIELDS, "cave")
    _require_addr(cave["vaddr"], "cave.vaddr")
    _require_addr(cave["file_offset"], "cave.file_offset")
    _require_size(cave["total_size"], "cave.total_size")
    if not isinstance(cave["fill"], str) or not re.fullmatch(r"[0-9a-f]{2}", cave["fill"]):
        raise ManifestShapeError("cave.fill must be two lowercase hex chars")

    trampoline = _require_object(manifest["trampoline"], "trampoline")
    _require_fields(trampoline, V1_TRAMPOLINE_FIELDS, "trampoline")
    _require_addr(trampoline["entry_vaddr"], "trampoline.entry_vaddr")
    _require_bytes(trampoline["blob"], "trampoline.blob")
    if not isinstance(trampoline["blob_sha256"], str) or not _HEX64.fullmatch(
        trampoline["blob_sha256"]
    ):
        raise ManifestShapeError("trampoline.blob_sha256 must be 64 lowercase hex chars")
    _require_size(trampoline["total_size"], "trampoline.total_size")

    if not isinstance(manifest["edits"], list) or not manifest["edits"]:
        raise ManifestShapeError("edits must be a non-empty list")
    for index, edit in enumerate(manifest["edits"]):
        edit = _require_object(edit, f"edits[{index}]")
        _require_fields(edit, V1_EDIT_FIELDS, f"edits[{index}]")
        _require_addr(edit["vaddr"], f"edits[{index}].vaddr")
        _require_addr(edit["file_offset"], f"edits[{index}].file_offset")
        _require_size(edit["size"], f"edits[{index}].size")
        _require_bytes(edit["original_bytes"], f"edits[{index}].original_bytes")
        _require_bytes(edit["patch_bytes"], f"edits[{index}].patch_bytes")

    _require_object(manifest["invariants"], "invariants")
    _require_object(manifest["reversibility"], "reversibility")
    preview = _require_object(manifest["preview"], "preview")
    _require_fields(preview, ("candidate_written",), "preview")
    if preview["candidate_written"] is not False:
        raise ManifestShapeError("preview.candidate_written must be false")
    if "candidate_sha256_if_applied" in preview:
        value = preview["candidate_sha256_if_applied"]
        if value is not None and (
            not isinstance(value, str) or not _HEX64.fullmatch(value)
        ):
            raise ManifestShapeError(
                "preview.candidate_sha256_if_applied must be null or 64 hex chars"
            )

    if "extensions" in manifest:
        _require_object(manifest["extensions"], "extensions")
    if "limits" in manifest:
        _require_object(manifest["limits"], "limits")
    if "warnings" in manifest and not isinstance(manifest["warnings"], list):
        raise ManifestShapeError("warnings must be a list")
    if "manifest_sha256" in manifest and (
        not isinstance(manifest["manifest_sha256"], str)
        or not _HEX64.fullmatch(manifest["manifest_sha256"])
    ):
        raise ManifestShapeError("manifest_sha256 must be 64 lowercase hex chars")


def to_edit_manifest_v1(manifest: dict[str, Any]) -> dict[str, Any]:
    """Map the provisional manifest to the public EditManifestV1 shape.

    The mapping is opt-in: ``build_manifest`` keeps the provisional output until
    M1 freezes/merges the schema.  Non-standard metadata is moved under
    ``extensions`` so no information is silently dropped.
    """
    validate_provisional_shape(manifest)
    # Required v1 identifiers; placeholders keep dry-run mapping possible before
    # a G2 plan exists, and are marked provisional under extensions.
    fixture_id = manifest.get("fixture_id") or "fixture-provisional"
    plan_id = manifest.get("plan_id") or "plan-provisional"
    if not isinstance(fixture_id, str) or not _FIXTURE_ID.fullmatch(fixture_id):
        raise ManifestShapeError("provisional manifest needs a valid fixture_id")
    if not isinstance(plan_id, str) or not plan_id:
        raise ManifestShapeError("provisional manifest needs a non-empty plan_id")

    extensions = copy.deepcopy(manifest.get("extensions", {}))
    if not isinstance(extensions, dict):
        raise ManifestShapeError("extensions must be an object")
    extensions["schema_mapping"] = {
        "source": PROVISIONAL_SCHEMA,
        "target": TARGET_SCHEMA,
        "status": TARGET_STATUS,
        "note": "Opt-in M5 mapping; EditManifestV1 freeze is pending M1.",
    }
    extensions["provisional"] = True

    mapped: dict[str, Any] = {
        "schema_version": EDIT_MANIFEST_V1_VERSION,
        "manifest_kind": TARGET_SCHEMA,
        "tool": manifest.get("tool"),
        "tool_version": manifest.get("tool_version"),
        "schema_note": "Provisional M5 dry-run mapping; EditManifestV1 freeze pending M1.",
        "dry_run": True,
        "fixture_id": fixture_id,
        "plan_id": plan_id,
        "original": copy.deepcopy(manifest["original"]),
        "patch_site": copy.deepcopy(manifest["patch_site"]),
        "cave": copy.deepcopy(manifest["cave"]),
        "trampoline": copy.deepcopy(manifest["trampoline"]),
        "edits": copy.deepcopy(manifest["edits"]),
        "invariants": copy.deepcopy(manifest["invariants"]),
        "reversibility": copy.deepcopy(manifest["reversibility"]),
        "preview": copy.deepcopy(manifest["preview"]),
        "verdict": None,
        "verdict_note": "M5 does not write or infer verdicts; M3 owns verification.",
        "extensions": extensions,
    }
    if manifest.get("contract") is not None:
        mapped["contract"] = copy.deepcopy(manifest["contract"])
    validate_edit_manifest_v1(mapped)
    return mapped
