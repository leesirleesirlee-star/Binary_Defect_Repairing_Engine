"""Apply an approved FixPlanV1 to the frozen fixture (G3 candidate).

The fixture is read-only.  The command writes, under an untracked artifact
directory:

* ``candidate.elf`` -- the plan's edits applied byte-for-byte;
* ``edit-manifest.json`` -- a truthful dry-run ``EditManifestV1``;
* ``candidate-v1.json`` -- the applied-candidate record from ADR 0004.

The command never executes the candidate and never writes a verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.repair.canonical import manifest_sha256
from pipeline.repair.elf64 import ELF64, Edit
from pipeline.repair.fixplan_reader import FixPlanError, FixPlanView, load_fix_plan
from pipeline.repair.manifest_schema import validate_edit_manifest_v1
from pipeline.repair.self_check import check_manifest

TOOL = "m5-apply-fixplan"
TOOL_VERSION = "0.1.0"


class ApplyError(ValueError):
    """Raised when a plan cannot be applied without breaking the fixture."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _segment_for(elf: ELF64, vaddr: int, size: int) -> Any:
    for segment in elf.pt_load_segments():
        if segment.p_vaddr <= vaddr and vaddr + size <= segment.p_vaddr + segment.p_filesz:
            return segment
    raise ApplyError(f"address range {_hex(vaddr)}+{size} is not in a file-backed PT_LOAD")


def _dynamic_sha(elf: ELF64) -> str | None:
    section = elf.section_by_name(".dynamic")
    if section is None:
        return None
    return _sha256(elf.section_bytes(section))


def _original_metadata(elf: ELF64, path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": elf.sha256(),
        "size": len(elf.data),
        "entry": _hex(elf.e_entry),
        "class": "ELF64",
        "machine": "EM_X86_64",
        "type": "ET_EXEC",
    }


def _resolve_edits(elf: ELF64, plan: FixPlanView) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    ranges: list[tuple[int, int]] = []
    for index, edit in enumerate(plan.edits):
        offset = elf.vaddr_to_offset(edit.address, max(edit.size, 1))
        if edit.size == 0:
            raise ApplyError(f"edits[{index}] is empty")
        end = offset + edit.size
        if end > len(elf.data):
            raise ApplyError(f"edits[{index}] runs past the fixture")
        actual = bytes(elf.data[offset:end])
        if edit.original_bytes:
            if actual != edit.original_bytes:
                raise ApplyError(
                    f"edits[{index}] original bytes do not match the frozen fixture"
                )
            original = edit.original_bytes
        else:
            if any(actual):
                raise ApplyError(
                    f"edits[{index}] has empty original_bytes but the tail is not zero-filled"
                )
            original = actual
        ranges.append((offset, end))
        resolved.append(
            {
                "kind": edit.kind,
                "address": edit.address,
                "file_offset": offset,
                "size": edit.size,
                "original_bytes": original,
                "new_bytes": edit.new_bytes,
                "reason": edit.reason or "",
            }
        )
    ordered = sorted(ranges)
    if any(
        ordered[index][0] < ordered[index - 1][1]
        for index in range(1, len(ordered))
    ):
        raise ApplyError("plan edits overlap")
    return resolved


def _build_manifest(
    elf_path: Path,
    plan: FixPlanView,
    resolved: list[dict[str, Any]],
    *,
    strcpy_plt: int,
    reserved_end: int,
    now: str,
) -> tuple[dict[str, Any], bytes, bytes]:
    elf = ELF64.from_path(elf_path)
    redirects = [item for item in resolved if item["kind"] == "redirect_call"]
    if len(redirects) != 1:
        raise ApplyError("plan must contain exactly one redirect_call edit")
    patch = redirects[0]
    if patch["address"] != plan.edit_site_vaddr:
        raise ApplyError("redirect is not at the plan edit site")
    patch_segment = _segment_for(elf, patch["address"], patch["size"])
    cave_vaddr = plan.cave_vaddr
    if cave_vaddr is None:
        raise ApplyError("plan has no cave")
    cave_edits = [item for item in resolved if item["kind"] in {"code", "data"}]
    if not cave_edits:
        raise ApplyError("plan has no code/data cave edits")
    cave_start = min(item["address"] for item in cave_edits)
    cave_end = max(item["address"] + item["size"] for item in cave_edits)
    if cave_start != cave_vaddr:
        raise ApplyError("cave does not start at the first code/data edit")
    if cave_end > reserved_end:
        raise ApplyError("cave runs past the reserved range")
    cave_size = cave_end - cave_start
    cave_segment = _segment_for(elf, cave_vaddr, cave_size)
    blob = bytearray(cave_size)
    code_size = 0
    message_size = 0
    message_vaddr: int | None = None
    for item in cave_edits:
        offset = item["address"] - cave_vaddr
        blob[offset:offset + item["size"]] = item["new_bytes"]
        if item["kind"] == "code":
            code_size += item["size"]
        else:
            message_size += item["size"]
            if message_vaddr is None:
                message_vaddr = item["address"]
    if code_size == 0 or message_size == 0:
        raise ApplyError("plan needs both guard code and data")
    blob_bytes = bytes(blob)

    preview = elf.preview_edits(
        [
            Edit(
                offset=item["file_offset"],
                new_bytes=item["new_bytes"],
                old_bytes=item["original_bytes"],
                name=item["kind"],
                purpose=item["reason"],
            )
            for item in resolved
        ]
    )
    preview_elf = ELF64(preview, source="<candidate-preview>")
    candidate_sha = _sha256(preview)
    before_dynamic = _dynamic_sha(elf)
    after_dynamic = _dynamic_sha(preview_elf)
    inverse = [
        Edit(
            offset=item["file_offset"],
            new_bytes=item["original_bytes"],
            old_bytes=item["new_bytes"],
            name=f"undo_{item['kind']}",
        )
        for item in resolved
    ]
    restored = preview_elf.preview_edits(inverse)
    if restored != elf.data:
        raise ApplyError("inverse edits did not restore the fixture")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "manifest_kind": "EditManifestV1",
        "tool": TOOL,
        "tool_version": TOOL_VERSION,
        "dry_run": True,
        "fixture_id": plan.fixture_id,
        "plan_id": plan.plan_id,
        "original": _original_metadata(elf, elf_path),
        "patch_site": {
            "vaddr": _hex(patch["address"]),
            "file_offset": _hex(patch["file_offset"]),
            "size": patch["size"],
            "segment_index": patch_segment.index,
            "segment_flags": patch_segment.flags_text,
            "original_bytes": patch["original_bytes"].hex(),
            "patch_bytes": patch["new_bytes"].hex(),
            "call_rel32": int.from_bytes(patch["new_bytes"][1:5], "little", signed=True),
            "target_cave_vaddr": _hex(cave_vaddr),
            "purpose": patch["reason"],
        },
        "cave": {
            "vaddr": _hex(cave_vaddr),
            "file_offset": _hex(elf.vaddr_to_offset(cave_vaddr, cave_size)),
            "segment_index": cave_segment.index,
            "segment_flags": cave_segment.flags_text,
            "total_size": cave_size,
            "code_size": code_size,
            "message_size": message_size,
            "message_vaddr": _hex(message_vaddr),
            "fill": "00",
            "reserved_end": _hex(reserved_end),
        },
        "trampoline": {
            "entry_vaddr": _hex(cave_vaddr),
            "blob": blob_bytes.hex(),
            "blob_sha256": _sha256(blob_bytes),
            "code_size": code_size,
            "message_size": message_size,
            "total_size": cave_size,
            "strcpy_plt_vaddr": _hex(strcpy_plt),
        },
        "edits": [
            {
                "name": f"{item['kind']}_{index}",
                "purpose": item["reason"],
                "vaddr": _hex(item["address"]),
                "file_offset": _hex(item["file_offset"]),
                "size": item["size"],
                "original_bytes": item["original_bytes"].hex(),
                "patch_bytes": item["new_bytes"].hex(),
            }
            for index, item in enumerate(resolved)
        ],
        "invariants": {
            "headers_sha256_before": elf.headers_sha256(),
            "headers_sha256_after": preview_elf.headers_sha256(),
            "headers_unchanged": elf.headers_bytes() == preview_elf.headers_bytes(),
            "entry_before": _hex(elf.e_entry),
            "entry_after": _hex(preview_elf.e_entry),
            "entry_unchanged": elf.e_entry == preview_elf.e_entry,
            "pt_load_count_before": len(elf.pt_load_segments()),
            "pt_load_count_after": len(preview_elf.pt_load_segments()),
            "pt_load_count_unchanged": len(elf.pt_load_segments())
            == len(preview_elf.pt_load_segments()),
            "pt_load_flags_before": [s.p_flags for s in elf.pt_load_segments()],
            "pt_load_flags_after": [s.p_flags for s in preview_elf.pt_load_segments()],
            "pt_load_flags_unchanged": [s.p_flags for s in elf.pt_load_segments()]
            == [s.p_flags for s in preview_elf.pt_load_segments()],
            "no_new_segments": len(elf.pt_load_segments()) == len(preview_elf.pt_load_segments()),
            "no_wx_segments": all(
                (s.p_flags & (1 | 2)) != (1 | 2) for s in preview_elf.pt_load_segments()
            ),
            "dynamic_sha256_before": before_dynamic,
            "dynamic_sha256_after": after_dynamic,
            "dynamic_unchanged": before_dynamic == after_dynamic,
            "no_new_imports": before_dynamic == after_dynamic,
            "edit_count": len(resolved),
            "changed_byte_count": sum(
                1 for a, b in zip(elf.data, preview, strict=True) if a != b
            ),
            "changed_bytes_covered": True,
        },
        "reversibility": {
            "method": "apply inverse edits to the in-memory preview",
            "restored_sha256": _sha256(restored),
            "matches_original": restored == elf.data,
            "inverse_edit_count": len(inverse),
        },
        "preview": {
            "candidate_sha256_if_applied": candidate_sha,
            "candidate_written": False,
        },
        "verdict": None,
        "verdict_note": "M5 does not write or infer verdicts; M3 owns verification.",
        "created_at": now,
        "extensions": {
            "g2_plan": {
                "plan_id": plan.plan_id,
                "contract_sha256": plan.contract_sha256,
            },
            "reserved_range": {"start": _hex(0x401211), "end": _hex(reserved_end)},
        },
    }
    if not manifest["invariants"]["headers_unchanged"]:
        raise ApplyError("candidate headers changed")
    if not manifest["invariants"]["dynamic_unchanged"]:
        raise ApplyError("candidate dynamic section changed")
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    validate_edit_manifest_v1(manifest)
    return manifest, preview, blob_bytes


def _validate_candidate_record(record: dict[str, Any]) -> None:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "CandidateV1.schema.json"
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - requirements include jsonschema
        raise ApplyError("jsonschema is required to validate CandidateV1") from exc
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(record)
    except jsonschema.ValidationError as exc:
        raise ApplyError(f"CandidateV1 validation failed: {exc.message}") from exc


def _build_candidate_record(
    *,
    plan_path: Path,
    manifest_path: Path,
    manifest_file_sha256: str,
    manifest: dict[str, Any],
    candidate_path: Path,
    candidate: bytes,
    original_path: Path,
    original: bytes,
    resolved: list[dict[str, Any]],
    now: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_kind": "CandidateV1",
        "candidate_written": True,
        "fixture_id": manifest["fixture_id"],
        "original": {
            "path": str(original_path),
            "sha256": _sha256(original),
            "size": len(original),
        },
        "candidate": {
            "path": str(candidate_path),
            "sha256": _sha256(candidate),
            "size": len(candidate),
        },
        "plan": {
            "path": str(plan_path),
            "sha256": _sha256(plan_path.read_bytes()),
            "plan_id": manifest["plan_id"],
        },
        "manifest": {
            "path": str(manifest_path),
            "sha256": manifest_file_sha256,
        },
        "edits_applied": [
            {
                "kind": item["kind"],
                "address": _hex(item["address"]),
                "file_offset": item["file_offset"],
                "size": item["size"],
                "new_sha256": _sha256(item["new_bytes"]),
            }
            for item in resolved
        ],
        "reversibility": {
            "matches_original": manifest["reversibility"]["matches_original"],
            "restored_sha256": manifest["reversibility"]["restored_sha256"],
            "method": manifest["reversibility"]["method"],
        },
        "produced_by": f"{TOOL} {TOOL_VERSION}",
        "produced_at": now,
        "notes": [
            "EditManifestV1 remains dry-run; CandidateV1 records the applied candidate (ADR 0004).",
            "manifest.sha256 is the file hash; manifest.manifest_sha256 is the canonical hash.",
        ],
    }


def apply_fix_plan(
    elf_path: str | Path,
    plan_path: str | Path,
    out_dir: str | Path,
    *,
    strcpy_plt: int = 0x401060,
    reserved_end: int = 0x402000,
    fixture_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Apply ``FixPlanV1`` to ``elf_path`` and write G3 artifacts."""
    elf_file = Path(elf_path)
    plan_file = Path(plan_path)
    out = Path(out_dir)
    plan = load_fix_plan(plan_file)
    if fixture_id is not None and plan.fixture_id != fixture_id:
        raise ApplyError(f"plan fixture_id {plan.fixture_id!r} != {fixture_id!r}")
    elf = ELF64.from_path(elf_file)
    original_sha = elf.sha256()
    resolved = _resolve_edits(elf, plan)
    now_value = now or datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
    out.mkdir(parents=True, exist_ok=True)
    candidate_path = out / "candidate.elf"
    manifest_path = out / "edit-manifest.json"
    record_path = out / "candidate-v1.json"
    if candidate_path.exists() or manifest_path.exists() or record_path.exists():
        raise ApplyError(f"refusing to overwrite existing artifacts in {out}")
    manifest, candidate, _ = _build_manifest(
        elf_file,
        plan,
        resolved,
        strcpy_plt=strcpy_plt,
        reserved_end=reserved_end,
        now=now_value,
    )
    self_check = check_manifest(elf_file, manifest)
    if self_check.get("status") != "checks_passed":
        raise ApplyError(f"self-check failed: {self_check.get('failures')}")
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_file_sha256 = _sha256(manifest_bytes)
    record = _build_candidate_record(
        plan_path=plan_file,
        manifest_path=manifest_path,
        manifest_file_sha256=manifest_file_sha256,
        manifest=manifest,
        candidate_path=candidate_path,
        candidate=candidate,
        original_path=elf_file,
        original=elf.data,
        resolved=resolved,
        now=now_value,
    )
    _validate_candidate_record(record)

    candidate_path.write_bytes(candidate)
    manifest_path.write_bytes(manifest_bytes)
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if _sha256(elf_file.read_bytes()) != original_sha:
        raise ApplyError("fixture changed during apply")
    return {
        "candidate_written": True,
        "candidate": str(candidate_path),
        "candidate_sha256": _sha256(candidate),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "manifest_file_sha256": manifest_file_sha256,
        "candidate_record": str(record_path),
        "candidate_record_sha256": _sha256(record_path.read_bytes()),
        "fixture_sha256": original_sha,
        "fixture_unchanged": True,
        "self_check": self_check["status"],
        "verdict": None,
        "executed_on_host": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply approved FixPlanV1 (G3, no execution)")
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--fixture-id")
    parser.add_argument("--strcpy-plt", type=lambda value: int(value, 0), default=0x401060)
    parser.add_argument("--reserved-end", type=lambda value: int(value, 0), default=0x402000)
    parser.add_argument("--now")
    args = parser.parse_args(argv)
    try:
        result = apply_fix_plan(
            args.elf,
            args.plan,
            args.out_dir,
            strcpy_plt=args.strcpy_plt,
            reserved_end=args.reserved_end,
            fixture_id=args.fixture_id,
            now=args.now,
        )
    except (ApplyError, FixPlanError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
