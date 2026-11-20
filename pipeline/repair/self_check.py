"""Structural self-check for an M5 dry-run edit manifest.

This tool applies the manifest to an in-memory copy of the original ELF and
checks structural invariants.  It is **not** a verdict: it does not run the
candidate, does not read M3's corpus and does not write ``verdict.json``.

The checks are intentionally mechanical:

* original hash and edit preimages match;
* every edit stays inside the image and edits do not overlap;
* ELF header, program headers, section headers, entry point, PT_LOAD count and
  segment permissions are unchanged;
* the preview has no W+X load segment and its dynamic section is unchanged;
* every changed byte is accounted for by a manifest edit;
* inverse edits restore the original hash exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.repair import EXIT_CHECK_FAILED, EXIT_ERROR, EXIT_OK, __version__
from pipeline.repair.canonical import manifest_sha256
from pipeline.repair.elf64 import ELF64, PF_W, PF_X, Edit, ELFError


class SelfCheckError(ValueError):
    """Raised when a manifest cannot be evaluated."""


def _sha256_hex(data: bytes) -> str:
    """Return a lowercase SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _edit_from_manifest(entry: dict[str, Any]) -> Edit:
    """Convert one manifest edit object into an :class:`Edit`."""
    try:
        offset = int(str(entry["file_offset"]), 0)
        original = bytes.fromhex(entry["original_bytes"])
        patch = bytes.fromhex(entry["patch_bytes"])
        name = str(entry.get("name", ""))
        purpose = str(entry.get("purpose", ""))
    except (KeyError, TypeError, ValueError) as exc:
        raise SelfCheckError(f"malformed edit entry: {entry!r}") from exc
    if len(original) != len(patch) or not patch:
        raise SelfCheckError(f"edit {name!r} has inconsistent byte lengths")
    return Edit(
        offset=offset,
        new_bytes=patch,
        old_bytes=original,
        name=name,
        purpose=purpose,
    )


def _changed_offsets(before: bytes, after: bytes) -> set[int]:
    """Return offsets whose byte changed between two equal-length blobs."""
    if len(before) != len(after):
        raise SelfCheckError("preview length changed")
    return {index for index, (old, new) in enumerate(zip(before, after, strict=True)) if old != new}


def _check_manifest(manifest: dict[str, Any], elf: ELF64) -> dict[str, Any]:
    """Run all structural checks and return a JSON-friendly report."""
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            failures.append(name if not detail else f"{name}: {detail}")

    if manifest.get("dry_run") is not True:
        record("dry_run_flag", False, "manifest must declare dry_run=true")
    else:
        record("dry_run_flag", True)

    expected_manifest_sha = manifest.get("manifest_sha256")
    if expected_manifest_sha:
        record(
            "manifest_sha256_matches",
            expected_manifest_sha == manifest_sha256(manifest),
            "" if expected_manifest_sha == manifest_sha256(manifest) else "manifest hash mismatch",
        )

    original = manifest.get("original", {})
    original_sha = str(original.get("sha256", ""))
    record(
        "original_sha256_matches",
        original_sha == elf.sha256(),
        "" if original_sha == elf.sha256() else "manifest original hash != input ELF",
    )

    raw_edits = manifest.get("edits")
    if not isinstance(raw_edits, list) or not raw_edits:
        return {
            "status": "checks_failed",
            "checks": checks + [{"name": "edits_present", "passed": False, "detail": "no edits"}],
            "failures": failures + ["edits_present: no edits"],
            "verdict_written_by_m5": False,
        }

    try:
        edits = [_edit_from_manifest(entry) for entry in raw_edits]
        record("edits_parse", True)
    except SelfCheckError as exc:
        record("edits_parse", False, str(exc))
        return {
            "status": "checks_failed",
            "checks": checks,
            "failures": failures,
            "verdict_written_by_m5": False,
        }

    # Preimage and range checks are implicit in preview_edits; call it first so
    # later checks only run on a structurally applicable manifest.
    try:
        preview_bytes = elf.preview_edits(edits)
        record("edit_preimages_and_ranges", True)
    except ELFError as exc:
        record("edit_preimages_and_ranges", False, str(exc))
        return {
            "status": "checks_failed",
            "checks": checks,
            "failures": failures,
            "verdict_written_by_m5": False,
        }

    try:
        preview = ELF64(preview_bytes, source="<self-check-preview>")
        record("preview_parses_as_elf64", True)
    except ELFError as exc:
        record("preview_parses_as_elf64", False, str(exc))
        return {
            "status": "checks_failed",
            "checks": checks,
            "failures": failures,
            "verdict_written_by_m5": False,
        }

    # Header, entry-point and segment invariants.
    record("headers_unchanged", elf.headers_bytes() == preview.headers_bytes())
    record("entry_unchanged", elf.e_entry == preview.e_entry)
    record(
        "pt_load_count_unchanged",
        len(elf.pt_load_segments()) == len(preview.pt_load_segments()),
    )
    before_flags = [segment.p_flags for segment in elf.pt_load_segments()]
    after_flags = [segment.p_flags for segment in preview.pt_load_segments()]
    record("pt_load_flags_unchanged", before_flags == after_flags)
    record(
        "no_wx_segments",
        all(
            (segment.p_flags & (PF_W | PF_X)) != (PF_W | PF_X)
            for segment in elf.pt_load_segments()
        ),
    )

    before_dynamic = elf.section_by_name(".dynamic")
    after_dynamic = preview.section_by_name(".dynamic")
    if before_dynamic is None and after_dynamic is None:
        record("dynamic_section_unchanged", True, ".dynamic absent in both")
    elif before_dynamic is None or after_dynamic is None:
        record("dynamic_section_unchanged", False, ".dynamic presence changed")
    else:
        record(
            "dynamic_section_unchanged",
            elf.section_bytes(before_dynamic) == preview.section_bytes(after_dynamic),
        )

    # Every changed byte must be in the union of manifest edit ranges.
    try:
        changed = _changed_offsets(elf.data, preview_bytes)
        allowed: set[int] = set()
        for edit in edits:
            allowed.update(range(edit.offset, edit.offset + edit.size))
        unaccounted = sorted(changed - allowed)
        record(
            "changed_bytes_covered",
            not unaccounted,
            "" if not unaccounted else f"{len(unaccounted)} byte(s) outside edits",
        )
    except SelfCheckError as exc:
        record("changed_bytes_covered", False, str(exc))

    # Inverse edits must restore the original bytes byte-for-byte.
    inverse = [
        Edit(
            offset=edit.offset,
            new_bytes=edit.old_bytes or b"",
            old_bytes=edit.new_bytes,
            name=f"undo_{edit.name}",
            purpose="self-check inverse",
        )
        for edit in edits
    ]
    try:
        restored = preview.preview_edits(inverse)
        record(
            "reversibility",
            restored == elf.data,
            "" if restored == elf.data else "inverse edits did not restore original",
        )
        record("restored_sha256_matches", _sha256_hex(restored) == elf.sha256())
    except ELFError as exc:
        record("reversibility", False, str(exc))

    preview_meta = manifest.get("preview", {})
    expected_preview_sha = preview_meta.get("candidate_sha256_if_applied")
    if expected_preview_sha:
        record(
            "preview_hash_matches_manifest",
            expected_preview_sha == _sha256_hex(preview_bytes),
        )
    candidate_written = preview_meta.get("candidate_written")
    candidate_detail = (
        "candidate_written=false"
        if candidate_written is False
        else "manifest claims a candidate was written"
    )
    record(
        "no_candidate_written_by_manifest",
        candidate_written is False,
        candidate_detail,
    )

    return {
        "status": "checks_passed" if not failures else "checks_failed",
        "checks": checks,
        "failures": failures,
        "preview_sha256": _sha256_hex(preview_bytes),
        "verdict_written_by_m5": False,
        "note": "Structural self-check only; M3 owns the verdict.",
    }


def check_manifest(elf_path: str | Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Load ``elf_path``, run the structural checks and return a report."""
    try:
        elf = ELF64.from_path(Path(elf_path))
    except (OSError, ELFError) as exc:
        return {
            "status": "error",
            "tool": "m5-self-check",
            "version": __version__,
            "error": str(exc),
            "verdict_written_by_m5": False,
        }
    report = _check_manifest(manifest, elf)
    report["tool"] = "m5-self-check"
    report["version"] = __version__
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; prints JSON and writes no files."""
    parser = argparse.ArgumentParser(description="M5 structural self-check (not a verdict)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, sort_keys=True))
        return EXIT_ERROR

    report = check_manifest(args.elf, manifest)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "checks_passed":
        return EXIT_OK
    if report["status"] == "error":
        return EXIT_ERROR
    return EXIT_CHECK_FAILED


if __name__ == "__main__":
    sys.exit(main())
