"""V0-V5 deterministic checks for the MVP2 fixture.

The verifier reads the frozen contract, the frozen corpus, the candidate
observations, the edit manifest and the two ELF byte images.  It never executes
an ELF, never reads the AI plan and never imports ``pipeline.repair``.

Rules that are enforced here rather than documented only:

* a check is ``pass`` only when its evidence was actually computed; missing
  evidence is ``not_run``;
* the V4 static check never guesses: an unrecognised guard layout is
  ``not_run``;
* nothing in this module writes a verdict label.  ``pipeline.verify.verdict``
  is the only writer, and it refuses to emit success without bound hashes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pipeline.verify.canonical import (
    FAIL,
    NOT_RUN,
    PASS,
    aggregate,
    argv_sha256,
    decode_b64,
    evidence_row,
    hex_bytes,
    hex_int,
    sha256_hex,
)
from pipeline.verify.elf64 import ELF64, EM_X86_64, ET_EXEC, ELFError

FIXTURE_ID = "stack-overflow-01"

#: ADR 0001 reserved zero-filled tail inside the single R-X PT_LOAD.  It is a
#: fixture-versioned constant: a new fixture needs a new verifier version.
RESERVED_TAIL = (0x401211, 0x402000)

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


class UnsupportedInput(Exception):
    """The request is outside the MVP2 verifier scope; verdict ``unsupported``."""


class VerifierError(Exception):
    """The verifier itself cannot continue; verdict ``error``."""


@dataclass(frozen=True)
class Inputs:
    """All verifier inputs for one candidate, bound by content hash."""

    contract: dict[str, Any]
    cases: dict[str, Any]
    observations: dict[str, Any]
    manifest: dict[str, Any]
    original_bytes: bytes
    candidate_bytes: bytes
    contract_sha256: str


@lru_cache(maxsize=8)
def load_schema(name: str) -> dict[str, Any]:
    """Load one frozen JSON Schema from ``schemas/``."""
    return json.loads((_SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate_document(document: Any, schema_name: str, label: str) -> None:
    """Validate an input document against a frozen schema or raise Unsupported."""
    errors = sorted(
        Draft202012Validator(load_schema(schema_name)).iter_errors(document), key=str
    )
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.path) or "<root>"
        raise UnsupportedInput(
            f"{label} does not validate against {schema_name}: {path}: {error.message}"
        )


def validate_inputs(inputs: Inputs) -> None:
    """Validate every input document and bind it to the in-scope fixture."""
    validate_document(inputs.contract, "ContractV1", "contract")
    validate_document(inputs.cases, "CaseSetV1", "cases")
    validate_document(inputs.observations, "ObservationV1", "observations")
    validate_document(inputs.manifest, "EditManifestV1", "manifest")
    for label, document in (
        ("contract", inputs.contract),
        ("cases", inputs.cases),
        ("manifest", inputs.manifest),
    ):
        if document["fixture_id"] != FIXTURE_ID:
            raise UnsupportedInput(
                f"{label} fixture_id is outside the MVP2 verifier scope "
                f"(expected {FIXTURE_ID})"
            )


def parse_original(original_bytes: bytes) -> ELF64:
    """Parse the original fixture; scope failures become Unsupported."""
    try:
        original = ELF64.from_bytes(original_bytes, source="original ELF")
    except ELFError as exc:
        raise UnsupportedInput(f"original ELF is outside scope: {exc}") from exc
    if original.e_type != ET_EXEC or original.e_machine != EM_X86_64:
        raise UnsupportedInput("original ELF is not an ELF64 x86-64 ET_EXEC image")
    return original


def parse_candidate(candidate_bytes: bytes) -> tuple[ELF64 | None, str | None]:
    """Parse the candidate; malformed bytes are a check failure, not a crash."""
    try:
        return ELF64.from_bytes(candidate_bytes, source="candidate ELF"), None
    except ELFError as exc:
        return None, str(exc)


def observed_case_map(
    observations: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Index observations by case id; report duplicate ids as a defect."""
    observed: dict[str, dict[str, Any]] = {}
    duplicates = False
    for case in observations["cases"]:
        case_id = case["id"]
        if case_id in observed:
            duplicates = True
        observed[case_id] = case
    return observed, duplicates


# ---------------------------------------------------------------------------
# V0 - identity
# ---------------------------------------------------------------------------
def check_identity(
    inputs: Inputs,
    original: ELF64,
    candidate: ELF64 | None,
    observed: dict[str, dict[str, Any]],
    duplicate_ids: bool,
) -> tuple[dict[str, Any], list[str], bool]:
    """V0: frozen hashes, case binding, headers and changed-byte coverage."""
    original_sha = sha256_hex(inputs.original_bytes)
    candidate_sha = sha256_hex(inputs.candidate_bytes)
    manifest_original = inputs.manifest["original"]
    preview_sha = inputs.manifest.get("preview", {}).get("candidate_sha256_if_applied")
    corpus = {case["id"]: case for case in inputs.cases["cases"]}

    checks: dict[str, bool | None] = {
        "original_matches_contract": original_sha == inputs.contract["binary_sha256"],
        "original_matches_manifest": (
            original_sha == manifest_original["sha256"]
            and len(inputs.original_bytes) == manifest_original["size"]
        ),
        "candidate_matches_observations": (
            candidate_sha == inputs.observations["binary"]["sha256"]
        ),
        "candidate_matches_manifest_preview": (
            None if preview_sha is None else candidate_sha == preview_sha
        ),
    }
    unknown_ids = sorted(set(observed) - set(corpus))
    checks["observation_ids_known"] = not unknown_ids and not duplicate_ids
    argv_mismatch = sorted(
        case_id
        for case_id, observed_case in observed.items()
        if case_id in corpus
        and observed_case.get("argv_sha256") != argv_sha256(corpus[case_id]["argv"])
    )
    checks["observation_argv_matches_corpus"] = not argv_mismatch

    same_size = len(inputs.original_bytes) == len(inputs.candidate_bytes)
    changed_count: int | None = None
    uncovered: list[int] = []
    if candidate is None:
        checks["headers_byte_identical"] = None
        checks["reserved_tail_zero_filled"] = None
        checks["changed_bytes_covered"] = None
    else:
        checks["headers_byte_identical"] = (
            same_size
            and original.header_without_entry() == candidate.header_without_entry()
            and original.program_header_bytes() == candidate.program_header_bytes()
            and original.section_header_bytes() == candidate.section_header_bytes()
        )
        changed = []
        if same_size:
            changed = [
                offset
                for offset, (before, after) in enumerate(
                    zip(inputs.original_bytes, inputs.candidate_bytes, strict=True)
                )
                if before != after
            ]
            changed_count = len(changed)
        tail_start, tail_end = _reserved_tail_offsets(original)
        checks["reserved_tail_zero_filled"] = tail_start is not None and all(
            byte == 0 for byte in inputs.original_bytes[tail_start:tail_end]
        )
        allowed: set[int] = set()
        for edit in inputs.manifest["edits"]:
            offset = hex_int(edit["file_offset"], "edits[].file_offset")
            allowed.update(range(offset, offset + edit["size"]))
        uncovered = [
            offset
            for offset in changed
            if offset not in allowed
            and not (tail_start is not None and tail_start <= offset < tail_end)
        ]
        checks["changed_bytes_covered"] = same_size and not uncovered

    status = _combine(checks)
    bound = (
        checks["original_matches_contract"]
        and checks["original_matches_manifest"]
        and checks["candidate_matches_observations"]
        and checks["candidate_matches_manifest_preview"] is True
    )
    evidence = {
        "checks": checks,
        "original_sha256": original_sha,
        "candidate_sha256": candidate_sha,
        "contract_binary_sha256": inputs.contract["binary_sha256"],
        "manifest_original_sha256": manifest_original["sha256"],
        "observations_binary_sha256": inputs.observations["binary"]["sha256"],
        "manifest_preview_sha256": preview_sha,
        "changed_byte_count": changed_count,
        "uncovered_offsets": [f"0x{offset:x}" for offset in uncovered[:32]],
        "uncovered_offset_count": len(uncovered),
        "unknown_observation_ids": unknown_ids,
        "duplicate_observation_ids": duplicate_ids,
        "argv_mismatch_case_ids": argv_mismatch,
        "reserved_tail": [f"0x{RESERVED_TAIL[0]:x}", f"0x{RESERVED_TAIL[1]:x}"],
    }
    return evidence_row("V0-identity", True, status, evidence), _check_notes(
        "V0-identity", checks
    ), bound


# ---------------------------------------------------------------------------
# V1 - structure
# ---------------------------------------------------------------------------
def check_structure(
    inputs: Inputs,
    original: ELF64,
    candidate: ELF64 | None,
    candidate_error: str | None,
) -> tuple[dict[str, Any], list[str]]:
    """V1: ELF shape, fixed headers, no new imports, manifest-bounded edits."""
    if candidate is None:
        evidence = {"candidate_parse_error": candidate_error}
        note = (
            f"V1-structure fail: candidate is not a readable ELF64 x86-64 image "
            f"({candidate_error})"
        )
        return evidence_row("V1-structure", True, FAIL, evidence), [note]

    manifest = inputs.manifest
    original_loads = original.load_segments()
    candidate_loads = candidate.load_segments()
    checks: dict[str, bool] = {
        "candidate_is_elf64_x86_64_exec": (
            candidate.e_type == ET_EXEC and candidate.e_machine == EM_X86_64
        ),
        "entry_unchanged": candidate.e_entry == original.e_entry,
        "pt_load_count_unchanged": len(original_loads) == len(candidate_loads),
        "pt_load_flags_unchanged": (
            [segment.p_flags for segment in original_loads]
            == [segment.p_flags for segment in candidate_loads]
        ),
        "no_wx_segments": all(
            not (segment.writable and segment.executable) for segment in candidate_loads
        ),
        "dynamic_section_unchanged": (
            _section_bytes(original, ".dynamic") == _section_bytes(candidate, ".dynamic")
        ),
        "dynsym_section_unchanged": (
            _section_bytes(original, ".dynsym") == _section_bytes(candidate, ".dynsym")
        ),
        "dynstr_section_unchanged": (
            _section_bytes(original, ".dynstr") == _section_bytes(candidate, ".dynstr")
        ),
        "dynamic_imports_unchanged": (
            original.dynamic_needed() == candidate.dynamic_needed()
        ),
    }
    text_relocations = [
        (name, offset)
        for name, offset in candidate.relocation_offsets()
        if candidate.vaddr_in_executable(offset)
    ]
    checks["no_text_relocations"] = not text_relocations

    patch_site = manifest["patch_site"]
    patch_vaddr = hex_int(patch_site["vaddr"], "patch_site.vaddr")
    patch_offset = hex_int(patch_site["file_offset"], "patch_site.file_offset")
    declared_original = hex_bytes(patch_site["original_bytes"], "patch_site.original_bytes")
    declared_patch = hex_bytes(patch_site["patch_bytes"], "patch_site.patch_bytes")
    patch_segment = candidate.segment_for_vaddr(patch_vaddr, 5)
    checks["patch_site_size_is_five"] = (
        patch_site["size"] == 5
        and len(declared_original) == 5
        and len(declared_patch) == 5
    )
    checks["patch_site_maps_to_file_offset"] = _maps_to(
        candidate, patch_vaddr, 5, patch_offset
    )
    checks["patch_site_inside_executable_segment"] = (
        patch_segment is not None and patch_segment.executable
    )
    checks["patch_site_original_bytes_match"] = (
        inputs.original_bytes[patch_offset:patch_offset + 5] == declared_original
    )
    checks["patch_site_patch_bytes_match"] = (
        inputs.candidate_bytes[patch_offset:patch_offset + 5] == declared_patch
    )

    actual_original_call = inputs.original_bytes[patch_offset:patch_offset + 5]
    actual_patch = inputs.candidate_bytes[patch_offset:patch_offset + 5]
    original_call_target = _rel32_target(patch_vaddr, actual_original_call)
    redirect_target = _rel32_target(patch_vaddr, actual_patch)
    checks["patch_is_e8_call"] = redirect_target is not None

    cave = manifest["cave"]
    trampoline = manifest["trampoline"]
    cave_vaddr = hex_int(cave["vaddr"], "cave.vaddr")
    cave_offset = hex_int(cave["file_offset"], "cave.file_offset")
    cave_size = cave["total_size"]
    blob = hex_bytes(trampoline["blob"], "trampoline.blob")
    entry_vaddr = hex_int(trampoline["entry_vaddr"], "trampoline.entry_vaddr")
    declared_copy_target = trampoline.get("strcpy_plt_vaddr")
    copy_target = (
        hex_int(declared_copy_target, "trampoline.strcpy_plt_vaddr")
        if declared_copy_target is not None
        else None
    )
    cave_segment = candidate.segment_for_file_range(cave_offset, cave_size)
    cave_vaddr_segment = candidate.segment_for_vaddr(cave_vaddr, cave_size)
    checks["cave_entry_matches_trampoline_entry"] = entry_vaddr == cave_vaddr
    checks["redirect_target_is_cave_entry"] = (
        redirect_target is not None and redirect_target == cave_vaddr
    )
    checks["original_call_target_matches_manifest"] = (
        original_call_target is not None
        and copy_target is not None
        and original_call_target == copy_target
    )
    checks["cave_maps_to_declared_file_offset"] = _maps_to(
        candidate, cave_vaddr, cave_size, cave_offset
    )
    checks["cave_inside_rx_segment"] = (
        cave_segment is not None
        and cave_segment.executable
        and not cave_segment.writable
        and cave_vaddr_segment is not None
        and cave_segment.index == cave_vaddr_segment.index
    )
    checks["cave_inside_reserved_tail"] = (
        RESERVED_TAIL[0] <= cave_vaddr
        and cave_vaddr + cave_size <= RESERVED_TAIL[1]
    )
    checks["cave_original_bytes_zero"] = all(
        byte == 0 for byte in inputs.original_bytes[cave_offset:cave_offset + cave_size]
    )
    checks["trampoline_size_consistent"] = (
        len(blob) == trampoline["total_size"] and len(blob) <= cave_size
    )
    checks["trampoline_bytes_match_candidate"] = (
        inputs.candidate_bytes[cave_offset:cave_offset + len(blob)] == blob
    )
    checks["trampoline_hash_matches"] = sha256_hex(blob) == trampoline["blob_sha256"]

    original_len = len(inputs.original_bytes)
    candidate_len = len(inputs.candidate_bytes)
    inverse = bytearray(inputs.candidate_bytes)
    forward = bytearray(inputs.original_bytes)
    preimages = postimages = mappings = True
    for edit in manifest["edits"]:
        offset = hex_int(edit["file_offset"], "edits[].file_offset")
        size = edit["size"]
        before = hex_bytes(edit["original_bytes"], "edits[].original_bytes")
        after = hex_bytes(edit["patch_bytes"], "edits[].patch_bytes")
        if len(before) != size or len(after) != size:
            preimages = postimages = False
            continue
        if offset < 0 or offset + size > original_len or offset + size > candidate_len:
            preimages = postimages = mappings = False
            continue
        if inputs.original_bytes[offset:offset + size] != before:
            preimages = False
        if inputs.candidate_bytes[offset:offset + size] != after:
            postimages = False
        if not _maps_to(candidate, hex_int(edit["vaddr"], "edits[].vaddr"), size, offset):
            mappings = False
        inverse[offset:offset + size] = inputs.original_bytes[offset:offset + size]
        forward[offset:offset + size] = after
    checks["edit_preimages_match_original"] = preimages
    checks["edit_postimages_match_candidate"] = postimages
    checks["edit_vaddrs_map_to_file_offsets"] = mappings
    checks["inverse_edits_restore_original"] = (
        original_len == candidate_len
        and sha256_hex(bytes(inverse)) == sha256_hex(inputs.original_bytes)
    )
    checks["applied_edits_reproduce_candidate"] = (
        original_len == candidate_len
        and sha256_hex(bytes(forward)) == sha256_hex(inputs.candidate_bytes)
    )

    status = _combine(checks)
    evidence = {
        "checks": checks,
        "entry_original": f"0x{original.e_entry:x}",
        "entry_candidate": f"0x{candidate.e_entry:x}",
        "pt_load_count_original": len(original_loads),
        "pt_load_count_candidate": len(candidate_loads),
        "patch_site": {
            "vaddr": f"0x{patch_vaddr:x}",
            "file_offset": f"0x{patch_offset:x}",
            "original_call_target": _hex_or_none(original_call_target),
            "redirect_target": _hex_or_none(redirect_target),
        },
        "cave": {
            "vaddr": f"0x{cave_vaddr:x}",
            "file_offset": f"0x{cave_offset:x}",
            "total_size": cave_size,
            "trampoline_size": len(blob),
        },
        "edit_count": len(manifest["edits"]),
        "text_relocations": [
            {"section": name, "offset": f"0x{offset:x}"}
            for name, offset in text_relocations[:8]
        ],
    }
    notes = []
    if status != PASS:
        failed = sorted(name for name, value in checks.items() if not value)
        notes.append("V1-structure fail: " + ", ".join(failed))
    return evidence_row("V1-structure", True, status, evidence), notes


# ---------------------------------------------------------------------------
# V2 - valid behaviour
# ---------------------------------------------------------------------------
def check_valid(
    inputs: Inputs, observed: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """V2: every valid case matches ``expected_candidate`` exactly."""
    valid_cases = [case for case in inputs.cases["cases"] if case["kind"] == "valid"]
    if not valid_cases:
        return evidence_row("V2-valid-behaviour", True, NOT_RUN, None), [
            "V2-valid-behaviour not_run: the frozen corpus has no valid cases"
        ]
    results = []
    for case in valid_cases:
        case_id = case["id"]
        observed_case = observed.get(case_id)
        if observed_case is None:
            results.append(
                {"id": case_id, "status": NOT_RUN, "differences": ["no observation"]}
            )
            continue
        differences = _valid_case_differences(observed_case, case["expected_candidate"])
        results.append(
            {
                "id": case_id,
                "status": FAIL if differences else PASS,
                "differences": differences,
            }
        )
    status = aggregate([result["status"] for result in results])
    return evidence_row(
        "V2-valid-behaviour", True, status, {"cases": results}
    ), _result_notes("V2-valid-behaviour", results)


# ---------------------------------------------------------------------------
# V3 - invalid response
# ---------------------------------------------------------------------------
def check_invalid(
    inputs: Inputs, observed: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    """V3: every invalid case (incl. the 64-byte PoC) rejects without a crash."""
    invalid_cases = [
        case for case in inputs.cases["cases"] if case["kind"] in ("invalid", "poc")
    ]
    if not invalid_cases:
        return evidence_row("V3-invalid-response", True, NOT_RUN, None), [
            "V3-invalid-response not_run: the frozen corpus has no invalid cases"
        ]
    invalid_stderr = inputs.contract["stated_criteria"]["invalid_stderr"].encode("utf-8")
    results = []
    for case in invalid_cases:
        case_id = case["id"]
        observed_case = observed.get(case_id)
        if observed_case is None:
            results.append(
                {"id": case_id, "status": NOT_RUN, "differences": ["no observation"]}
            )
            continue
        differences = _invalid_case_differences(observed_case, invalid_stderr)
        results.append(
            {
                "id": case_id,
                "status": FAIL if differences else PASS,
                "differences": differences,
            }
        )
    status = aggregate([result["status"] for result in results])
    evidence = {
        "contract_invalid_stderr_sha256": sha256_hex(invalid_stderr),
        "case_ids": [case["id"] for case in invalid_cases],
        "cases": results,
    }
    return evidence_row("V3-invalid-response", True, status, evidence), _result_notes(
        "V3-invalid-response", results
    )


# ---------------------------------------------------------------------------
# V4 - boundary
# ---------------------------------------------------------------------------
def check_boundary(
    inputs: Inputs,
    candidate: ELF64 | None,
    candidate_error: str | None,
    observed: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """V4: 31 accepted / 32 rejected plus a static compare-before-copy check."""
    stated = inputs.contract["stated_criteria"]
    max_valid = stated["max_valid_input_bytes"]
    capacity = stated["capacity_bytes"]
    includes_terminator = stated["capacity_includes_terminator"]
    implied_max = capacity - (1 if includes_terminator else 0)
    if implied_max != max_valid:
        note = (
            "V4-boundary not_run: contract capacity "
            f"{capacity} (terminator={includes_terminator}) does not imply "
            f"max_valid_input_bytes {max_valid}"
        )
        return evidence_row("V4-boundary", True, NOT_RUN, None), [note]

    cases = inputs.cases["cases"]
    invalid_stderr = stated["invalid_stderr"].encode("utf-8")
    valid_case = _boundary_case(cases, "valid", max_valid)
    invalid_case = _boundary_case(cases, "invalid", max_valid + 1)
    dynamic_results: list[dict[str, Any]] = []
    for boundary, case in (("valid", valid_case), ("invalid", invalid_case)):
        if case is None:
            dynamic_results.append(
                {
                    "boundary": boundary,
                    "status": NOT_RUN,
                    "reason": "no boundary case in the frozen corpus",
                }
            )
            continue
        case_id = case["id"]
        observed_case = observed.get(case_id)
        if observed_case is None:
            dynamic_results.append(
                {
                    "boundary": boundary,
                    "case": case_id,
                    "status": NOT_RUN,
                    "reason": "no observation for this case",
                }
            )
            continue
        if boundary == "valid":
            differences = _valid_case_differences(
                observed_case, case["expected_candidate"]
            )
        else:
            differences = _invalid_case_differences(observed_case, invalid_stderr)
        dynamic_results.append(
            {
                "boundary": boundary,
                "case": case_id,
                "status": FAIL if differences else PASS,
                "differences": differences,
            }
        )
    dynamic_status = aggregate([result["status"] for result in dynamic_results])
    static_status, static_evidence, static_reason = _static_guard_check(
        inputs, candidate, candidate_error, max_valid
    )
    status = aggregate([dynamic_status, static_status])
    evidence = {
        "boundary": {
            "capacity_bytes": capacity,
            "max_valid_input_bytes": max_valid,
        },
        "dynamic": dynamic_results,
        "static": static_evidence,
    }
    notes = []
    for result in dynamic_results:
        if result["status"] == NOT_RUN:
            notes.append(
                f"V4-boundary not_run: {result['boundary']} boundary case not "
                f"measured ({result['reason']})"
            )
        elif result["status"] == FAIL:
            notes.append(
                f"V4-boundary fail: {result['boundary']} boundary case "
                f"{result.get('case')} mismatched ({', '.join(result['differences'])})"
            )
    if static_status == NOT_RUN:
        notes.append(f"V4-boundary not_run: {static_reason}")
    elif static_status == FAIL:
        notes.append(f"V4-boundary fail: {static_reason}")
    return evidence_row("V4-boundary", True, status, evidence), notes


def _static_guard_check(
    inputs: Inputs,
    candidate: ELF64 | None,
    candidate_error: str | None,
    max_valid: int,
) -> tuple[str, dict[str, Any], str | None]:
    """Check the redirect lands in the cave and a length compare precedes copy."""
    if candidate is None:
        return (
            NOT_RUN,
            {},
            f"candidate is not a readable ELF64 image ({candidate_error})",
        )
    manifest = inputs.manifest
    patch_site = manifest["patch_site"]
    cave = manifest["cave"]
    trampoline = manifest["trampoline"]
    try:
        patch_vaddr = hex_int(patch_site["vaddr"], "patch_site.vaddr")
        patch_offset = hex_int(patch_site["file_offset"], "patch_site.file_offset")
        cave_vaddr = hex_int(cave["vaddr"], "cave.vaddr")
        cave_offset = hex_int(cave["file_offset"], "cave.file_offset")
        cave_size = cave["total_size"]
        blob = hex_bytes(trampoline["blob"], "trampoline.blob")
        code_size = trampoline.get("code_size")
        if not isinstance(code_size, int) or code_size <= 0:
            code_size = len(blob)
    except (KeyError, ValueError, TypeError) as exc:
        return NOT_RUN, {}, f"manifest fields needed by the static check are bad: {exc}"
    actual_patch = inputs.candidate_bytes[patch_offset:patch_offset + 5]
    actual_original = inputs.original_bytes[patch_offset:patch_offset + 5]
    redirect_target = _rel32_target(patch_vaddr, actual_patch)
    copy_target = _rel32_target(patch_vaddr, actual_original)
    if redirect_target is None or copy_target is None:
        return (
            NOT_RUN,
            {"patch_site": {"vaddr": f"0x{patch_vaddr:x}"}},
            "patch site/original call is not a 5-byte E8 call",
        )
    evidence: dict[str, Any] = {
        "patch_site": {
            "vaddr": f"0x{patch_vaddr:x}",
            "redirect_target": f"0x{redirect_target:x}",
        },
        "declared_cave": {
            "vaddr": f"0x{cave_vaddr:x}",
            "total_size": cave_size,
        },
        "copy_target": f"0x{copy_target:x}",
    }
    if not cave_vaddr <= redirect_target < cave_vaddr + cave_size:
        return (
            FAIL,
            evidence,
            f"redirect target 0x{redirect_target:x} is outside the declared cave",
        )
    if code_size > cave_size or cave_offset + code_size > len(inputs.candidate_bytes):
        return (
            NOT_RUN,
            evidence,
            "declared trampoline code region is not readable in the candidate",
        )
    code = inputs.candidate_bytes[cave_offset:cave_offset + code_size]
    evidence["code_size"] = code_size
    jumps = []
    for offset in range(0, len(code) - 4):
        if code[offset] != 0xE9:
            continue
        target = cave_vaddr + offset + 5 + int.from_bytes(
            code[offset + 1:offset + 5], "little", signed=True
        )
        if target == copy_target:
            jumps.append(offset)
    comparison = _boundary_compare(code, (max_valid, max_valid + 1))
    if comparison is not None:
        evidence["comparison_offset"] = comparison[0]
        evidence["comparison_immediate"] = comparison[1]
        evidence["comparison_encoding"] = comparison[2]
    if comparison is None:
        return (
            NOT_RUN,
            evidence,
            "no comparison against the 31/32-byte boundary found in the cave code",
        )
    if not jumps:
        return (
            NOT_RUN,
            evidence,
            "no rel32 tail jump to the copy target found in the cave code",
        )
    comparison_offset = comparison[0]
    jump_offset = min(jumps)
    evidence["tail_jump_offset"] = jump_offset
    if comparison_offset >= jump_offset:
        return (
            FAIL,
            evidence,
            f"boundary comparison at code offset {comparison_offset} does not "
            f"precede the copy tail jump at {jump_offset}",
        )
    early_calls = [
        offset
        for offset in range(0, comparison_offset - 4)
        if code[offset] == 0xE8
        and cave_vaddr + offset + 5
        + int.from_bytes(code[offset + 1:offset + 5], "little", signed=True)
        == copy_target
    ]
    if early_calls:
        return (
            FAIL,
            evidence,
            f"direct call to the copy target at code offset {early_calls[0]} "
            "precedes the boundary check",
        )
    return PASS, evidence, None


def _boundary_compare(code: bytes, boundary: tuple[int, int]) -> tuple[int, int, str] | None:
    """Find a ``cmp reg, imm`` against 31/32; pattern match, not full decode.

    Two G3-approved guard layouts must be recognised:

    * the legacy ``pipeline.repair.guard`` layout, which compares the scanned
      length with ``cmp eax, 32`` (``83 f8 20``);
    * the G2-selected plan's guard, which compares ``rdx`` with 31
      (``48 83 fa 1f``) after ``inc rdx``.

    The caller only accepts the compare when it precedes the tail jump to the
    original copy target, so the encoding set can stay generic: any register
    compare-immediate form with 31/32 as the immediate is a candidate.
    """
    for offset in range(len(code)):
        found = _compare_immediate(code, offset)
        if found is not None and found[0] in boundary:
            return offset, found[0], found[1]
    return None


def _compare_immediate(code: bytes, offset: int) -> tuple[int, str] | None:
    """Decode compare-immediate encodings acceptable as a boundary check.

    Returns ``(immediate, encoding)`` or None.  Only register-direct compare
    forms are decoded; a memory compare or the printable check ``cmp al, 0x20``
    is not accepted as a length check, which keeps the static evidence honest.
    """
    if (
        offset + 4 <= len(code)
        and code[offset] == 0x48
        and code[offset + 1] == 0x83
        and 0xF8 <= code[offset + 2] <= 0xFF
    ):
        return code[offset + 3], "REX.W 83 /7 ib"  # cmp r64, imm8
    if (
        offset + 3 <= len(code)
        and code[offset] == 0x83
        and 0xF8 <= code[offset + 1] <= 0xFF
    ):
        return code[offset + 2], "83 /7 ib"  # cmp r32, imm8
    if (
        offset + 7 <= len(code)
        and code[offset] == 0x48
        and code[offset + 1] == 0x81
        and 0xF8 <= code[offset + 2] <= 0xFF
    ):
        return (
            int.from_bytes(code[offset + 3:offset + 7], "little"),
            "REX.W 81 /7 id",
        )  # cmp r64, imm32
    if (
        offset + 6 <= len(code)
        and code[offset] == 0x81
        and 0xF8 <= code[offset + 1] <= 0xFF
    ):
        return (
            int.from_bytes(code[offset + 2:offset + 6], "little"),
            "81 /7 id",
        )  # cmp r32, imm32
    if offset + 5 <= len(code) and code[offset] == 0x3D:
        return (
            int.from_bytes(code[offset + 1:offset + 5], "little"),
            "3d id",
        )  # cmp eax, imm32
    if offset + 6 <= len(code) and code[offset] == 0x48 and code[offset + 1] == 0x3D:
        return (
            int.from_bytes(code[offset + 2:offset + 6], "little"),
            "REX.W 3d id",
        )  # cmp rax, imm32
    return None


# ---------------------------------------------------------------------------
# V5 - re-apply reproducibility (optional)
# ---------------------------------------------------------------------------
def check_reapply(
    inputs: Inputs, candidate_sha: str
) -> tuple[dict[str, Any], list[str]]:
    """V5: applying the manifest to the original reproduces the candidate hash."""
    rebuilt = bytearray(inputs.original_bytes)
    for edit in inputs.manifest["edits"]:
        try:
            offset = hex_int(edit["file_offset"], "edits[].file_offset")
            size = edit["size"]
            after = hex_bytes(edit["patch_bytes"], "edits[].patch_bytes")
        except (KeyError, ValueError, TypeError) as exc:
            note = f"V5-reapply not_run: manifest edit is not usable ({exc})"
            return evidence_row("V5-reapply", False, NOT_RUN, None), [note]
        if len(after) != size or offset < 0 or offset + size > len(rebuilt):
            note = "V5-reapply not_run: manifest edit is out of bounds or size-inconsistent"
            return evidence_row("V5-reapply", False, NOT_RUN, None), [note]
        rebuilt[offset:offset + size] = after
    rebuilt_sha = sha256_hex(bytes(rebuilt))
    status = PASS if rebuilt_sha == candidate_sha else FAIL
    evidence = {
        "rebuilt_candidate_sha256": rebuilt_sha,
        "actual_candidate_sha256": candidate_sha,
        "edit_count": len(inputs.manifest["edits"]),
    }
    notes = []
    if status == FAIL:
        notes.append(
            f"V5-reapply fail: rebuilt hash {rebuilt_sha} != candidate {candidate_sha}"
        )
    return evidence_row("V5-reapply", False, status, evidence), notes


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def compute_coverage(
    cases: dict[str, Any],
    observed: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report measured cases and not_run criteria in the VerdictV1 coverage shape."""
    corpus_ids = [case["id"] for case in cases["cases"]]
    missing = [case_id for case_id in corpus_ids if case_id not in observed]
    not_run = [row["id"] for row in rows if row["status"] == NOT_RUN]
    return {
        "cases_total": len(corpus_ids),
        "cases_run": len(corpus_ids) - len(missing),
        "unmeasured": missing + not_run,
    }


def _check_notes(criterion: str, checks: dict[str, bool | None]) -> list[str]:
    """Turn failed/unknown sub-checks into deterministic limitation lines."""
    notes = []
    failed = sorted(name for name, value in checks.items() if value is False)
    unknown = sorted(name for name, value in checks.items() if value is None)
    if failed:
        notes.append(f"{criterion} fail: " + ", ".join(failed))
    if unknown:
        notes.append(f"{criterion} not_run: " + ", ".join(unknown))
    return notes


def _result_notes(criterion: str, results: list[dict[str, Any]]) -> list[str]:
    """Turn per-case results into deterministic limitation lines."""
    notes = []
    not_run = sorted(result["id"] for result in results if result["status"] == NOT_RUN)
    failed = sorted(result["id"] for result in results if result["status"] == FAIL)
    if not_run:
        notes.append(f"{criterion} not_run: no observation for {', '.join(not_run)}")
    if failed:
        notes.append(f"{criterion} fail: mismatch on {', '.join(failed)}")
    return notes


def _valid_case_differences(observed: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Compare one observed valid case with ``expected_candidate``."""
    differences = []
    if observed.get("timed_out"):
        differences.append("timed_out is true")
    if observed.get("signal") is not None:
        differences.append(f"signal is {observed.get('signal')}")
    if observed.get("exit_code") != expected.get("exit_code"):
        differences.append(
            f"exit_code {observed.get('exit_code')!r} != {expected.get('exit_code')!r}"
        )
    for observed_field, expected_field in (
        ("stdout_b64", "stdout"),
        ("stderr_b64", "stderr"),
    ):
        want = expected.get(expected_field, "").encode("utf-8")
        try:
            got = decode_b64(observed.get(observed_field, ""))
        except ValueError:
            differences.append(f"{observed_field} is not valid base64")
            continue
        if got != want:
            differences.append(f"{expected_field} differs")
    return differences


def _invalid_case_differences(observed: dict[str, Any], invalid_stderr: bytes) -> list[str]:
    """Compare one observed invalid case with the stated rejection criteria."""
    differences = []
    if observed.get("timed_out"):
        differences.append("timed_out is true")
    if observed.get("signal") is not None:
        differences.append(f"signal is {observed.get('signal')}")
    if observed.get("exit_code") != 1:
        differences.append(f"exit_code {observed.get('exit_code')!r} != 1")
    try:
        stdout = decode_b64(observed.get("stdout_b64", ""))
    except ValueError:
        stdout = None
        differences.append("stdout_b64 is not valid base64")
    if stdout is not None and stdout != b"":
        differences.append("stdout is not empty")
    try:
        stderr = decode_b64(observed.get("stderr_b64", ""))
    except ValueError:
        stderr = None
        differences.append("stderr_b64 is not valid base64")
    if stderr is not None and stderr != invalid_stderr:
        differences.append("stderr does not match contract invalid_stderr")
    return differences


def _boundary_case(
    cases: list[dict[str, Any]], kind: str, length: int
) -> dict[str, Any] | None:
    """Return the first corpus case of ``kind`` whose argv[0] has ``length`` bytes."""
    kinds = ("valid",) if kind == "valid" else ("invalid", "poc")
    for case in cases:
        if case["kind"] not in kinds:
            continue
        argv = case.get("argv") or []
        if argv and len(argv[0].encode("utf-8")) == length:
            return case
    return None


def _section_bytes(elf: ELF64, name: str) -> bytes | None:
    """Return the raw bytes of a named section (None when absent)."""
    return elf.section_bytes(elf.section_by_name(name))


def _maps_to(elf: ELF64, vaddr: int, size: int, offset: int) -> bool:
    """Return true when the ELF maps ``vaddr`` at file ``offset``."""
    try:
        return elf.vaddr_to_offset(vaddr, size) == offset
    except ELFError:
        return False


def _rel32_target(instruction_vaddr: int, instruction: bytes) -> int | None:
    """Decode an ``E8``/``E9`` rel32 branch target, or None when not applicable."""
    if len(instruction) != 5 or instruction[0] not in (0xE8, 0xE9):
        return None
    return instruction_vaddr + 5 + int.from_bytes(instruction[1:5], "little", signed=True)


def _reserved_tail_offsets(original: ELF64) -> tuple[int | None, int | None]:
    """Map the ADR 0001 reserved tail vaddr range to file offsets."""
    start_vaddr, end_vaddr = RESERVED_TAIL
    try:
        start = original.vaddr_to_offset(start_vaddr, 1)
        last = original.vaddr_to_offset(end_vaddr - 1, 1)
    except ELFError:
        return None, None
    return start, last + 1


def _combine(checks: dict[str, bool | None]) -> str:
    """Combine boolean sub-checks; ``None`` means the check could not run."""
    if any(value is False for value in checks.values()):
        return FAIL
    if any(value is None for value in checks.values()):
        return NOT_RUN
    return PASS


def _hex_or_none(value: int | None) -> str | None:
    """Format an optional address as lowercase hex."""
    return None if value is None else f"0x{value:x}"
