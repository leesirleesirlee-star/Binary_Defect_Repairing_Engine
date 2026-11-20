"""Dry-run patch writer for the reserved R-X guard.

This module turns an approved patch site and an approved cave address into an
edit manifest.  It **never** writes ``candidate.elf``, never edits the original
file and never executes anything.  The manifest is a proposal for M3's verifier,
not a verdict.

The only edits it can emit are:

* one 5-byte ``call`` replacement at the approved patch site;
* one guard blob inside the approved reserved cave.

Program headers, section headers, the entry point and dynamic imports are not
editable here.  A candidate would keep them byte-identical to the original by
construction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.repair import EXIT_ERROR, EXIT_OK, __version__
from pipeline.repair.canonical import manifest_sha256
from pipeline.repair.elf64 import (
    ELF64,
    ET_EXEC,
    PF_W,
    PF_X,
    Edit,
    ELFError,
    encode_rel32_branch,
    fits_rel32,
)
from pipeline.repair.guard import (
    CODE_LIMIT,
    DATA_LIMIT,
    GuardError,
    build_guard,
)
from pipeline.repair.manifest_schema import (
    normalize_provisional,
    validate_provisional_shape,
)


class PatchWriterError(ValueError):
    """Raised when a requested dry-run patch violates the approved boundary."""


def _sha256_hex(data: bytes) -> str:
    """Return a lowercase SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _hex(data: bytes) -> str:
    """Return a compact lowercase hex string for manifest fields."""
    return data.hex()


def _ranges_overlap(
    start_a: int,
    end_a: int,
    start_b: int,
    end_b: int,
) -> bool:
    """Return true when two half-open file/virtual ranges intersect."""
    return start_a < end_b and start_b < end_a


def _load_contract_hash(contract_path: str | Path | None) -> dict[str, str] | None:
    """Return path/hash metadata for an optional contract file."""
    if contract_path is None:
        return None
    path = Path(contract_path)
    data = path.read_bytes()
    return {"path": str(path), "sha256": _sha256_hex(data), "size": len(data)}


def _dynamic_hash(elf: ELF64) -> str | None:
    """Return the hash of ``.dynamic`` when the ELF has that section."""
    section = elf.section_by_name(".dynamic")
    if section is None:
        return None
    return _sha256_hex(elf.section_bytes(section))


def _changed_offsets(before: bytes, after: bytes) -> set[int]:
    """Return the set of byte offsets that differ between two equal-length blobs."""
    if len(before) != len(after):
        raise PatchWriterError("preview length changed; header edits are not allowed")
    return {index for index, (old, new) in enumerate(zip(before, after, strict=True)) if old != new}


def _covered_by_edits(offsets: set[int], edits: list[Edit]) -> bool:
    """Return true when every changed offset belongs to an emitted edit."""
    allowed: set[int] = set()
    for edit in edits:
        allowed.update(range(edit.offset, edit.offset + edit.size))
    return offsets <= allowed


def _invariants(elf: ELF64, preview: ELF64, edits: list[Edit]) -> dict[str, Any]:
    """Compare structural invariants between the original and in-memory preview."""
    before_flags = [(segment.index, segment.p_flags) for segment in elf.pt_load_segments()]
    after_flags = [(segment.index, segment.p_flags) for segment in preview.pt_load_segments()]
    no_wx = all(
        (segment.p_flags & (PF_W | PF_X)) != (PF_W | PF_X)
        for segment in elf.pt_load_segments()
    )
    changed = _changed_offsets(elf.data, preview.data)
    dynamic_before = _dynamic_hash(elf)
    dynamic_after = _dynamic_hash(preview)
    return {
        "headers_sha256_before": elf.headers_sha256(),
        "headers_sha256_after": preview.headers_sha256(),
        "headers_unchanged": elf.headers_bytes() == preview.headers_bytes(),
        "entry_before": f"0x{elf.e_entry:x}",
        "entry_after": f"0x{preview.e_entry:x}",
        "entry_unchanged": elf.e_entry == preview.e_entry,
        "pt_load_count_before": len(elf.pt_load_segments()),
        "pt_load_count_after": len(preview.pt_load_segments()),
        "pt_load_count_unchanged": len(elf.pt_load_segments()) == len(preview.pt_load_segments()),
        "pt_load_flags_before": [flags for _, flags in before_flags],
        "pt_load_flags_after": [flags for _, flags in after_flags],
        "pt_load_flags_unchanged": before_flags == after_flags,
        "no_new_segments": len(elf.pt_load_segments()) == len(preview.pt_load_segments()),
        "no_wx_segments": no_wx,
        "dynamic_sha256_before": dynamic_before,
        "dynamic_sha256_after": dynamic_after,
        "dynamic_unchanged": dynamic_before == dynamic_after,
        "no_new_imports": dynamic_before == dynamic_after,
        "edit_count": len(edits),
        "changed_byte_count": len(changed),
        "changed_bytes_covered": _covered_by_edits(changed, edits),
    }


def build_manifest(
    elf_path: str | Path,
    *,
    patch_site_vaddr: int,
    cave_vaddr: int,
    strcpy_plt_vaddr: int,
    fixture_id: str | None = None,
    contract_path: str | Path | None = None,
    expected_site_bytes: bytes | None = None,
    cave_limit_vaddr: int | None = None,
    plan_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a dry-run edit manifest.

    Parameters
    ----------
    elf_path:
        Original ELF; only read from.
    patch_site_vaddr:
        Virtual address of the original 5-byte ``call`` to redirect.
    cave_vaddr:
        Virtual address of the approved guard start; must be 16-byte aligned.
    strcpy_plt_vaddr:
        Target address used by the original call (normally ``strcpy@plt``).
    fixture_id:
        Optional fixture identifier copied into the manifest.
    contract_path:
        Optional contract file; only its path/hash is recorded.
    expected_site_bytes:
        Optional exact original bytes; when omitted, a leading ``0xE8`` is
        required and the bytes are read from the ELF.
    cave_limit_vaddr:
        Optional end of the approved reserved range; the guard must fit before it.
    plan_id:
        Optional approved G2 plan identifier.
    created_at:
        Optional ISO-8601 timestamp for evidence.  When omitted, the manifest
        is byte-for-byte deterministic for the same input.

    Raises
    ------
    PatchWriterError
        If the site, cave, target or encoding violates the approved boundary.
    """
    path = Path(elf_path)
    try:
        elf = ELF64.from_path(path)
    except (OSError, ELFError) as exc:
        raise PatchWriterError(str(exc)) from exc

    if elf.e_type != ET_EXEC:
        raise PatchWriterError("M5 targets non-PIE ET_EXEC only")

    if patch_site_vaddr < 0 or cave_vaddr < 0 or strcpy_plt_vaddr < 0:
        raise PatchWriterError("virtual addresses must be non-negative")

    # --- validate the patch site ----------------------------------------
    try:
        patch_segment = elf.segment_for_vaddr(patch_site_vaddr, 5, file_backed=True)
        patch_offset = elf.vaddr_to_offset(patch_site_vaddr, 5)
    except ELFError as exc:
        raise PatchWriterError(f"patch site is not file-backed: {exc}") from exc
    if not patch_segment.executable:
        raise PatchWriterError("patch site is not inside an executable segment")
    site_bytes = elf.read_vaddr(patch_site_vaddr, 5)
    if site_bytes[0] != 0xE8:
        raise PatchWriterError(f"patch site does not start with E8: {site_bytes.hex()}")
    if expected_site_bytes is not None and site_bytes != expected_site_bytes:
        raise PatchWriterError(
            f"patch-site bytes differ: expected {expected_site_bytes.hex()}, got {site_bytes.hex()}"
        )

    # --- validate the target --------------------------------------------
    try:
        target_segment = elf.segment_for_vaddr(strcpy_plt_vaddr, 1, file_backed=True)
    except ELFError as exc:
        raise PatchWriterError(f"strcpy target is not file-backed: {exc}") from exc
    if not target_segment.executable:
        raise PatchWriterError("strcpy target is not executable")

    # --- validate the cave ----------------------------------------------
    if cave_vaddr % 16 != 0:
        raise PatchWriterError(f"cave 0x{cave_vaddr:x} is not 16-byte aligned")
    try:
        cave_segment = elf.segment_for_vaddr(cave_vaddr, 1, file_backed=True)
    except ELFError as exc:
        raise PatchWriterError(f"cave is not file-backed: {exc}") from exc
    if not cave_segment.executable:
        raise PatchWriterError("cave is not inside an executable segment")
    if cave_segment.index != patch_segment.index:
        raise PatchWriterError("cave and patch site must be in the same R-X PT_LOAD")

    try:
        guard = build_guard(cave_vaddr, strcpy_plt_vaddr)
    except GuardError as exc:
        raise PatchWriterError(str(exc)) from exc
    if cave_vaddr + guard.total_size > cave_segment.p_vaddr + cave_segment.p_filesz:
        raise PatchWriterError("guard does not fit in the file-backed executable segment")
    if cave_limit_vaddr is not None and cave_vaddr + guard.total_size > cave_limit_vaddr:
        raise PatchWriterError(
            f"guard ends at 0x{cave_vaddr + guard.total_size:x}, beyond approved "
            f"limit 0x{cave_limit_vaddr:x}"
        )
    if cave_limit_vaddr is not None and cave_limit_vaddr <= cave_vaddr:
        raise PatchWriterError("cave_limit_vaddr must be greater than cave_vaddr")

    try:
        cave_offset = elf.vaddr_to_offset(cave_vaddr, guard.total_size)
        cave_old = elf.read_vaddr(cave_vaddr, guard.total_size)
    except ELFError as exc:
        raise PatchWriterError(f"cave is not file-backed: {exc}") from exc
    if any(byte != 0 for byte in cave_old):
        raise PatchWriterError("cave is not zero-filled; refusing to emit a manifest")

    cave_file_end = cave_offset + guard.total_size
    header_tables = [
        (0, elf.e_ehsize, "ELF header"),
        (elf.e_phoff, elf.e_phnum * elf.e_phentsize, "program header table"),
        (elf.e_shoff, elf.e_shnum * elf.e_shentsize, "section header table"),
    ]
    for table_start, table_size, label in header_tables:
        if table_size and _ranges_overlap(
            cave_offset,
            cave_file_end,
            table_start,
            table_start + table_size,
        ):
            raise PatchWriterError(f"cave overlaps the {label}")

    if elf.sections_overlapping(cave_vaddr, guard.total_size):
        raise PatchWriterError("cave overlaps an allocated section")
    try:
        for relocation in elf.relocations():
            if _ranges_overlap(
                cave_vaddr,
                cave_vaddr + guard.total_size,
                relocation.vaddr,
                relocation.vaddr + relocation.width,
            ):
                raise PatchWriterError(
                    f"cave overlaps relocation in {relocation.section!r}"
                )
    except ELFError as exc:
        raise PatchWriterError(f"cannot inspect relocations: {exc}") from exc

    # The patch site and cave must not overlap.
    site_start = patch_site_vaddr
    site_end = patch_site_vaddr + 5
    cave_end = cave_vaddr + guard.total_size
    if site_start < cave_end and cave_vaddr < site_end:
        raise PatchWriterError("patch site and cave overlap")

    # --- encode the redirecting call ------------------------------------
    call_rel32 = cave_vaddr - (patch_site_vaddr + 5)
    if not fits_rel32(patch_site_vaddr + 5, cave_vaddr):
        raise PatchWriterError("cave is outside the rel32 range of the patch site")
    try:
        patch_bytes = encode_rel32_branch(0xE8, patch_site_vaddr, cave_vaddr)
    except ELFError as exc:
        raise PatchWriterError(str(exc)) from exc

    edits = [
        Edit(
            offset=patch_offset,
            new_bytes=patch_bytes,
            old_bytes=site_bytes,
            name="patch_site",
            purpose="replace one 5-byte call with a call to the M5 guard",
        ),
        Edit(
            offset=cave_offset,
            new_bytes=guard.blob,
            old_bytes=cave_old,
            name="cave_guard",
            purpose="write the guard code and frozen stderr message into the reserved cave",
        ),
    ]

    # --- in-memory preview and invariants -------------------------------
    try:
        preview_bytes = elf.preview_edits(edits)
        preview = ELF64(preview_bytes, source="<in-memory-preview>")
    except ELFError as exc:
        raise PatchWriterError(f"preview is not a valid ELF: {exc}") from exc

    invariants = _invariants(elf, preview, edits)
    if not invariants["headers_unchanged"]:
        raise PatchWriterError("preview changed ELF headers; this is forbidden")
    if not invariants["entry_unchanged"]:
        raise PatchWriterError("preview changed the entry point; this is forbidden")
    if not invariants["pt_load_count_unchanged"]:
        raise PatchWriterError("preview changed the PT_LOAD count; this is forbidden")
    if not invariants["pt_load_flags_unchanged"]:
        raise PatchWriterError("preview changed segment permissions; this is forbidden")
    if not invariants["changed_bytes_covered"]:
        raise PatchWriterError("preview contains bytes not accounted for by the manifest")
    if not invariants["no_wx_segments"]:
        raise PatchWriterError("original has a W+X PT_LOAD; fixture is unsupported")

    # --- reversibility ---------------------------------------------------
    inverse = [
        Edit(
            offset=edit.offset,
            new_bytes=edit.old_bytes or b"",
            old_bytes=edit.new_bytes,
            name=f"undo_{edit.name}",
            purpose="reversibility check",
        )
        for edit in edits
    ]
    try:
        restored = preview.preview_edits(inverse)
    except ELFError as exc:
        raise PatchWriterError(f"inverse preview failed: {exc}") from exc
    reversibility = {
        "method": "apply inverse edits to the in-memory preview",
        "restored_sha256": _sha256_hex(restored),
        "matches_original": restored == elf.data,
        "inverse_edit_count": len(inverse),
    }
    if not reversibility["matches_original"]:
        raise PatchWriterError("inverse edits do not restore the original bytes")

    # --- manifest --------------------------------------------------------
    warnings = [
        "Dry-run only: no candidate file was written and no code was executed.",
        "The guard assumes the approved source string is NUL-terminated within 32 bytes.",
        "A failing or closed stderr cannot produce the contract's exact bytes; M3 must reject it.",
        "The caller must verify this manifest against the approved G2 plan and contract.",
    ]
    manifest: dict[str, Any] = {
        "schema_version": "m5-dryrun-v0",
        "manifest_kind": "EditManifestV1-draft",
        "tool": "m5-patch-writer",
        "tool_version": __version__,
        "schema_note": (
            "Provisional M5 dry-run shape; replace with M1's frozen EditManifestV1 "
            "when that schema is published."
        ),
        "dry_run": True,
        "fixture_id": fixture_id or path.stem,
        "plan_id": plan_id,
        "original": {
            "path": str(path),
            "sha256": elf.sha256(),
            "size": len(elf.data),
            "entry": f"0x{elf.e_entry:x}",
            "class": "ELF64",
            "machine": "EM_X86_64",
            "type": "ET_EXEC",
        },
        "contract": _load_contract_hash(contract_path),
        "patch_site": {
            "vaddr": f"0x{patch_site_vaddr:x}",
            "file_offset": f"0x{patch_offset:x}",
            "size": 5,
            "segment_index": patch_segment.index,
            "segment_flags": patch_segment.flags_text,
            "original_bytes": _hex(site_bytes),
            "patch_bytes": _hex(patch_bytes),
            "call_rel32": call_rel32,
            "target_cave_vaddr": f"0x{cave_vaddr:x}",
            "purpose": "redirect the original strcpy call to the guard",
        },
        "cave": {
            "vaddr": f"0x{cave_vaddr:x}",
            "file_offset": f"0x{cave_offset:x}",
            "segment_index": cave_segment.index,
            "segment_flags": cave_segment.flags_text,
            "total_size": guard.total_size,
            "code_size": guard.code_size,
            "message_size": guard.message_size,
            "message_vaddr": f"0x{guard.message_vaddr:x}",
            "fill": "00",
            "reserved_end": (
                f"0x{cave_limit_vaddr:x}" if cave_limit_vaddr is not None else None
            ),
        },
        "trampoline": {
            "entry_vaddr": f"0x{cave_vaddr:x}",
            "blob": _hex(guard.blob),
            "blob_sha256": _sha256_hex(guard.blob),
            "code_size": guard.code_size,
            "message_size": guard.message_size,
            "total_size": guard.total_size,
            "jmp_plt_offset": guard.jmp_plt_offset,
            "jmp_plt_rel32": guard.jmp_plt_rel32,
            "strcpy_plt_vaddr": f"0x{strcpy_plt_vaddr:x}",
            "labels": guard.labels,
        },
        "edits": [
            {
                "name": edit.name,
                "purpose": edit.purpose,
                "vaddr": (
                    f"0x{patch_site_vaddr:x}"
                    if edit.name == "patch_site"
                    else f"0x{cave_vaddr:x}"
                ),
                "file_offset": f"0x{edit.offset:x}",
                "size": edit.size,
                "original_bytes": _hex(edit.old_bytes or b""),
                "patch_bytes": _hex(edit.new_bytes),
            }
            for edit in edits
        ],
        "invariants": invariants,
        "reversibility": reversibility,
        "preview": {
            "candidate_sha256_if_applied": _sha256_hex(preview_bytes),
            "candidate_written": False,
        },
        "limits": {"code_bytes": CODE_LIMIT, "data_bytes": DATA_LIMIT},
        "warnings": warnings,
        "verdict": None,
        "verdict_note": "M5 does not write or infer verdicts; M3 owns verification.",
    }
    manifest = normalize_provisional(manifest)
    validate_provisional_shape(manifest)
    if created_at is not None:
        manifest["created_at"] = created_at
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    return manifest


def write_manifest(manifest: dict[str, Any], out_path: str | Path) -> Path:
    """Write only the JSON manifest, never a candidate ELF."""
    path = Path(out_path)
    if path.suffix.lower() in {".elf", ".bin", ".so", ".o"}:
        raise PatchWriterError("refusing to write a manifest with a binary suffix")
    original = manifest.get("original", {}).get("path")
    if original and path.resolve() == Path(original).resolve():
        raise PatchWriterError("manifest output must not overwrite the original ELF")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; emits a JSON manifest and never a candidate."""
    parser = argparse.ArgumentParser(description="Dry-run ELF64 patch manifest writer")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--patch-site", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--cave", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--strcpy-plt", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--cave-limit", type=lambda value: int(value, 0))
    parser.add_argument("--fixture-id")
    parser.add_argument("--plan-id")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--expected-site-bytes")
    parser.add_argument("--created-at")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    expected = (
        bytes.fromhex(args.expected_site_bytes)
        if args.expected_site_bytes is not None
        else None
    )
    try:
        manifest = build_manifest(
            args.elf,
            patch_site_vaddr=args.patch_site,
            cave_vaddr=args.cave,
            strcpy_plt_vaddr=args.strcpy_plt,
            fixture_id=args.fixture_id,
            contract_path=args.contract,
            expected_site_bytes=expected,
            cave_limit_vaddr=args.cave_limit,
            plan_id=args.plan_id,
            created_at=args.created_at,
        )
        out = write_manifest(manifest, args.out)
    except (PatchWriterError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, indent=2, sort_keys=True))
        return EXIT_ERROR

    summary = {
        "status": "manifest_written",
        "tool": "m5-patch-writer",
        "version": __version__,
        "manifest": str(out),
        "dry_run": True,
        "candidate_written": False,
        "original_sha256": manifest["original"]["sha256"],
        "patch_site": manifest["patch_site"]["vaddr"],
        "cave": manifest["cave"]["vaddr"],
        "guard_size": manifest["cave"]["total_size"],
        "reversible": manifest["reversibility"]["matches_original"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
