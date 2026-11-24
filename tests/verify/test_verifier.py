"""Verifier tests for V0-V5 on the frozen fixture.

Nothing here executes an ELF: the candidate bytes are the frozen original with
the declared edits applied in memory, and the manifest/observations are
synthetic in-memory documents.  The runtime guest run belongs to ``guest/``.

The synthetic candidate uses the guard byte layout frozen in
``docs/repair/guard-abi.md`` purely as test data; the verifier does not import
``pipeline.repair``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from pipeline.verify.canonical import verdict_sha256
from pipeline.verify.verdict import main, verify_candidate

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01"
CONTRACT_BYTES = (FIXTURE / "contract.json").read_bytes()
CASES_BYTES = (FIXTURE / "cases" / "cases.json").read_bytes()
ORIGINAL = (FIXTURE / "vuln.elf").read_bytes()
VERDICT_SCHEMA = json.loads(
    (ROOT / "schemas" / "VerdictV1.schema.json").read_text(encoding="utf-8")
)

PATCH_VADDR, PATCH_OFFSET = 0x401194, 0x1194
CAVE_VADDR, CAVE_OFFSET = 0x401220, 0x1220
STRCPY_PLT = 0x401060
MESSAGE = b"ERROR: input exceeds destination capacity\n"
GUARD_CODE_SIZE = 69
NOW = "2026-11-21T12:00:00Z"
NOT_RUN = "not_run"
PASS = "pass"
FAIL = "fail"
LIVE_OBSERVATIONS = (
    ROOT / "docs" / "plan" / "evidence" / "g3" / "observations-candidate-wsl2.json"
)
LIVE_CANDIDATE_SHA = "c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28"


# ---------------------------------------------------------------------------
# Synthetic fixture builders (bytes only; no execution)
# ---------------------------------------------------------------------------
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _patch_bytes(cave_vaddr: int = CAVE_VADDR) -> bytes:
    return b"\xe8" + struct.pack("<i", cave_vaddr - (PATCH_VADDR + 5))


def _guard_blob(cave_vaddr: int = CAVE_VADDR, copy_vaddr: int = STRCPY_PLT) -> bytes:
    """Return the documented guard layout: 69 code bytes + 42 message bytes."""
    prefix = bytes.fromhex(
        "31c0803c06007438ffc083f82072f3"
        "bf02000000488d352a000000ba2a000000"
        "b8010000000f0585c07e074801c629c275ee"
        "b8e7000000bf010000000f050f0b"
    )
    jump = b"\xe9" + struct.pack("<i", copy_vaddr - (cave_vaddr + 64 + 5))
    assert len(prefix) == 64
    return prefix + jump + MESSAGE


#: The frozen G2-selected plan's guard (run 2), stored as plain test data:
#: 90 code bytes (endbr64, printable-ASCII length scan, `cmp rdx, 31` bound,
#: `e9` tail-jump to strcpy@plt, then the write/exit reject path) plus the
#: frozen 42-byte message at the 16-byte-aligned address 0x401280.
#: Provenance: frozen G2 plan (run 2); b8 3c=exit(60), b8 01=write(1); no plan file read.
SELECTED_PLAN_GUARD_HEX = (
    "f30f1efa4889f131d28a0184c074223c200f821f0000003c7e0f871700000048ffc2"
    "4883fa1f0f870a00000048ffc1ebd8e90afeffffb801000000bf02000000488d35"
    "19000000ba2a0000000f05b83c000000bf010000000f05"
)
SELECTED_PLAN_CODE_SIZE = 90
SELECTED_PLAN_MESSAGE_OFFSET = 96


def _selected_plan_guard() -> bytes:
    """Return the selected plan's 90-byte guard plus its aligned message."""
    code = bytes.fromhex(SELECTED_PLAN_GUARD_HEX)
    assert len(code) == SELECTED_PLAN_CODE_SIZE
    padding = bytes(SELECTED_PLAN_MESSAGE_OFFSET - len(code))
    return code + padding + MESSAGE


def _apply_edits(data: bytes, edits: list[tuple[int, bytes]]) -> bytes:
    patched = bytearray(data)
    for offset, payload in edits:
        patched[offset:offset + len(payload)] = payload
    return bytes(patched)


def _candidate(
    *,
    blob: bytes | None = None,
    extra_edits: list[tuple[int, bytes]] | None = None,
    patch_bytes: bytes | None = None,
    cave_vaddr: int = CAVE_VADDR,
) -> bytes:
    blob = _guard_blob() if blob is None else blob
    patch = _patch_bytes() if patch_bytes is None else patch_bytes
    edits = [(PATCH_OFFSET, patch), (cave_vaddr - 0x400000, blob)]
    edits.extend(extra_edits or [])
    return _apply_edits(ORIGINAL, edits)


def _vaddr_for_offset(offset: int) -> str:
    if offset < 0x538:
        return f"0x{0x400000 + offset:x}"
    if 0x1000 <= offset < 0x2000:
        return f"0x{0x401000 + offset - 0x1000:x}"
    return f"0x{0x402000 + offset - 0x2000:x}"


def _manifest(
    candidate_bytes: bytes,
    *,
    blob: bytes | None = None,
    code_size: int | None = None,
    message_size: int | None = None,
    message_offset: int | None = None,
    extra_edits: list[tuple[int, bytes]] | None = None,
    cave_vaddr: int = CAVE_VADDR,
    cave_offset: int | None = None,
    patch_bytes: bytes | None = None,
    preview_sha: str | None = "auto",
) -> dict[str, Any]:
    blob = _guard_blob() if blob is None else blob
    patch = _patch_bytes() if patch_bytes is None else patch_bytes
    if cave_offset is None:
        cave_offset = cave_vaddr - 0x400000
    if code_size is None:
        code_size = GUARD_CODE_SIZE if blob == _guard_blob() else len(blob)
    if message_size is None:
        message_size = len(MESSAGE) if code_size == GUARD_CODE_SIZE else 0
    if message_offset is None:
        message_offset = code_size
    edits = [(PATCH_OFFSET, patch), (cave_offset, blob)]
    edits.extend(extra_edits or [])
    edit_entries = []
    for index, (offset, payload) in enumerate(edits):
        name = ("patch_site", "cave_guard")[index] if index < 2 else f"edit_{index}"
        edit_entries.append(
            {
                "name": name,
                "purpose": "synthetic verifier-test edit",
                "vaddr": _vaddr_for_offset(offset),
                "file_offset": f"0x{offset:x}",
                "size": len(payload),
                "original_bytes": ORIGINAL[offset:offset + len(payload)].hex(),
                "patch_bytes": payload.hex(),
            }
        )
    candidate_sha = _sha(candidate_bytes)
    trampoline: dict[str, Any] = {
        "entry_vaddr": f"0x{cave_vaddr:x}",
        "blob": blob.hex(),
        "blob_sha256": _sha(blob),
        "code_size": code_size,
        "message_size": message_size,
        "total_size": len(blob),
        "strcpy_plt_vaddr": f"0x{STRCPY_PLT:x}",
        "labels": {},
    }
    if code_size >= 5:
        trampoline["jmp_plt_offset"] = code_size - 5
        trampoline["jmp_plt_rel32"] = STRCPY_PLT - (cave_vaddr + code_size)
    return {
        "schema_version": 1,
        "manifest_kind": "EditManifestV1",
        "tool": "verifier-test-fixture",
        "dry_run": True,
        "fixture_id": "stack-overflow-01",
        "plan_id": "plan-test-verifier",
        "original": {
            "path": "fixtures/stack-overflow-01/vuln.elf",
            "sha256": _sha(ORIGINAL),
            "size": len(ORIGINAL),
            "entry": "0x401090",
            "class": "ELF64",
            "machine": "EM_X86_64",
            "type": "ET_EXEC",
        },
        "patch_site": {
            "vaddr": f"0x{PATCH_VADDR:x}",
            "file_offset": f"0x{PATCH_OFFSET:x}",
            "size": 5,
            "segment_index": 3,
            "segment_flags": "R-X",
            "original_bytes": ORIGINAL[PATCH_OFFSET:PATCH_OFFSET + 5].hex(),
            "patch_bytes": patch.hex(),
            "call_rel32": cave_vaddr - (PATCH_VADDR + 5),
            "target_cave_vaddr": f"0x{cave_vaddr:x}",
        },
        "cave": {
            "vaddr": f"0x{cave_vaddr:x}",
            "file_offset": f"0x{cave_offset:x}",
            "segment_index": 3,
            "segment_flags": "R-X",
            "total_size": len(blob),
            "code_size": code_size,
            "message_size": message_size,
            "message_vaddr": f"0x{cave_vaddr + message_offset:x}",
            "fill": "00",
            "reserved_end": "0x402000",
        },
        "trampoline": trampoline,
        "edits": edit_entries,
        "invariants": {},
        "reversibility": {},
        "preview": {
            "candidate_sha256_if_applied": None if preview_sha is None else candidate_sha,
            "candidate_written": False,
        },
        "warnings": [],
        "verdict": None,
    }


def _observations(
    candidate_sha: str,
    mutate: Any = None,
    *,
    started_at: str = "2026-11-21T00:00:00Z",
) -> dict[str, Any]:
    corpus = json.loads(CASES_BYTES)
    cases = []
    for case in corpus["cases"]:
        expected = case["expected_candidate"]
        observed = {
            "id": case["id"],
            "argv_sha256": _sha(json.dumps(case["argv"], separators=(",", ":")).encode()),
            "exit_code": expected.get("exit_code"),
            "signal": expected.get("signal"),
            "stdout_b64": base64.b64encode(
                expected.get("stdout", "").encode("utf-8")
            ).decode("ascii"),
            "stderr_b64": base64.b64encode(
                expected.get("stderr", "").encode("utf-8")
            ).decode("ascii"),
            "duration_ms": 3,
            "timed_out": False,
        }
        if mutate is not None:
            mutate(case["id"], observed)
        cases.append(observed)
    return {
        "schema_version": 1,
        "binary": {"path": "candidate.elf", "sha256": candidate_sha},
        "environment": {"uname": "Linux verifier-test", "kernel": "test", "libc": "glibc test"},
        "started_at": started_at,
        "cases": cases,
    }


def _default_kwargs() -> dict[str, Any]:
    blob = _guard_blob()
    candidate = _candidate(blob=blob)
    return {
        "contract": json.loads(CONTRACT_BYTES),
        "cases": json.loads(CASES_BYTES),
        "observations": _observations(_sha(candidate)),
        "manifest": _manifest(candidate, blob=blob),
        "original_bytes": ORIGINAL,
        "candidate_bytes": candidate,
        "contract_sha256": _sha(CONTRACT_BYTES),
        "now": NOW,
    }


def _kwargs_for(
    candidate: bytes,
    *,
    manifest: dict[str, Any] | None = None,
    manifest_kwargs: dict[str, Any] | None = None,
    observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs = _default_kwargs()
    kwargs["candidate_bytes"] = candidate
    kwargs["manifest"] = (
        manifest
        if manifest is not None
        else _manifest(candidate, **(manifest_kwargs or {}))
    )
    kwargs["observations"] = (
        observations if observations is not None else _observations(_sha(candidate))
    )
    return kwargs


def _verify(**overrides: Any) -> dict[str, Any]:
    kwargs = _default_kwargs()
    kwargs.update(overrides)
    return verify_candidate(**kwargs)


def _status(verdict: dict[str, Any], criterion_id: str) -> str:
    return next(row["status"] for row in verdict["criteria"] if row["id"] == criterion_id)


def _required(verdict: dict[str, Any], criterion_id: str) -> bool:
    return next(row["required"] for row in verdict["criteria"] if row["id"] == criterion_id)


def _notes_contain(verdict: dict[str, Any], needle: str) -> bool:
    return any(needle in note for note in verdict["limitations"])


def _schema_errors(verdict: dict[str, Any]) -> list:
    return sorted(Draft202012Validator(VERDICT_SCHEMA).iter_errors(verdict), key=str)


def _assert_schema_valid(verdict: dict[str, Any]) -> None:
    assert not _schema_errors(verdict), [str(error) for error in _schema_errors(verdict)]


# ---------------------------------------------------------------------------
# Pass path, schema and reproducibility
# ---------------------------------------------------------------------------
def test_all_required_checks_pass_with_evidence() -> None:
    verdict = _verify()
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "verified_against_stated_criteria"
    assert {row["id"]: row["status"] for row in verdict["criteria"]} == {
        "V0-identity": PASS,
        "V1-structure": PASS,
        "V2-valid-behaviour": PASS,
        "V3-invalid-response": PASS,
        "V4-boundary": PASS,
        "V5-reapply": PASS,
    }
    for row in verdict["criteria"]:
        assert row["evidence_sha256"] is not None
    assert verdict["original_sha256"] == _sha(ORIGINAL)
    assert verdict["candidate_sha256"] == _sha(_candidate())
    assert verdict["contract_sha256"] == _sha(CONTRACT_BYTES)
    assert verdict["produced_at"] == NOW
    assert verdict["produced_by"] == "pipeline.verify.verdict"
    assert verdict["coverage"] == {"cases_total": 9, "cases_run": 9, "unmeasured": []}


def test_v5_is_reported_but_not_required() -> None:
    verdict = _verify()
    assert _required(verdict, "V5-reapply") is False


def test_live_style_selected_plan_observations_pass_v0_v5() -> None:
    """A live-style observation document still has to satisfy every check."""
    blob = _selected_plan_guard()
    candidate = _candidate(blob=blob)
    observations = _observations(_sha(candidate))
    observations["environment"] = {
        "uname": "Linux guest 6.18.40.1-microsoft-standard-WSL2 x86_64",
        "kernel": "6.18.40.1-microsoft-standard-WSL2",
        "libc": "glibc 2.43",
    }
    observations["started_at"] = "2026-11-22T11:06:48Z"
    verdict = verify_candidate(
        **_kwargs_for(
            candidate,
            manifest_kwargs={
                "blob": blob,
                "code_size": SELECTED_PLAN_CODE_SIZE,
                "message_size": len(MESSAGE),
                "message_offset": SELECTED_PLAN_MESSAGE_OFFSET,
            },
            observations=observations,
        )
    )
    assert verdict["verdict"] == "verified_against_stated_criteria"
    assert {row["id"]: row["status"] for row in verdict["criteria"]} == {
        "V0-identity": PASS,
        "V1-structure": PASS,
        "V2-valid-behaviour": PASS,
        "V3-invalid-response": PASS,
        "V4-boundary": PASS,
        "V5-reapply": PASS,
    }
    assert verdict["coverage"] == {"cases_total": 9, "cases_run": 9, "unmeasured": []}


def test_live_wsl2_observation_is_bound_to_the_g3_candidate() -> None:
    """The committed live observation is schema-valid and bound to the candidate."""
    payload = json.loads(LIVE_OBSERVATIONS.read_text(encoding="utf-8"))
    schema = json.loads(
        (ROOT / "schemas" / "ObservationV1.schema.json").read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(schema).iter_errors(payload))
    assert payload["binary"]["sha256"] == LIVE_CANDIDATE_SHA
    assert payload["environment"]["kernel"].endswith("WSL2")
    assert len(payload["cases"]) == 9
    assert {case["id"] for case in payload["cases"]} == {
        "valid-0",
        "valid-1",
        "valid-5",
        "valid-31",
        "valid-punct",
        "invalid-32",
        "invalid-33",
        "invalid-64",
        "invalid-128",
    }


def test_live_observation_candidate_hash_mismatch_is_refused() -> None:
    observations = json.loads(LIVE_OBSERVATIONS.read_text(encoding="utf-8"))
    observations["binary"]["sha256"] = "0" * 64
    verdict = _verify(observations=observations)
    assert _status(verdict, "V0-identity") == FAIL
    assert verdict["verdict"] != "verified_against_stated_criteria"


def test_selected_plan_guard_layout_passes_v4() -> None:
    """G3 applies the G2-selected plan's 90-byte guard, not the legacy layout."""
    blob = _selected_plan_guard()
    candidate = _candidate(blob=blob)
    kwargs = _kwargs_for(
        candidate,
        manifest_kwargs={
            "blob": blob,
            "code_size": SELECTED_PLAN_CODE_SIZE,
            "message_size": len(MESSAGE),
            "message_offset": SELECTED_PLAN_MESSAGE_OFFSET,
        },
    )
    verdict = verify_candidate(**kwargs)
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "verified_against_stated_criteria"
    for criterion in ("V0-identity", "V1-structure", "V4-boundary"):
        assert _status(verdict, criterion) == PASS


def test_selected_plan_layout_without_length_compare_is_v4_not_run() -> None:
    """The printable checks are not a substitute for the 31-byte length bound."""
    code = bytearray(bytes.fromhex(SELECTED_PLAN_GUARD_HEX))
    code[34:38] = b"\x48\x90\x90\x90"  # NOP out `cmp rdx, 0x1f`, keep the layout
    blob = (
        bytes(code)
        + bytes(SELECTED_PLAN_MESSAGE_OFFSET - len(code))
        + MESSAGE
    )
    candidate = _candidate(blob=blob)
    kwargs = _kwargs_for(
        candidate,
        manifest_kwargs={
            "blob": blob,
            "code_size": SELECTED_PLAN_CODE_SIZE,
            "message_size": len(MESSAGE),
            "message_offset": SELECTED_PLAN_MESSAGE_OFFSET,
        },
    )
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V4-boundary") == NOT_RUN
    assert verdict["verdict"] == "unverified"
    assert _notes_contain(verdict, "no comparison against the 31/32-byte boundary")


def test_extended_compare_immediate_encoding_passes_v4() -> None:
    """`cmp rdx, 31` may be encoded as REX.W 81 /7 id; that still proves the bound."""
    compare = b"\x48\x81\xfa\x1f\x00\x00\x00"
    tail = b"\xe9" + struct.pack(
        "<i", STRCPY_PLT - (CAVE_VADDR + len(compare) + 5)
    )
    code = compare + tail
    candidate = _candidate(blob=code)
    kwargs = _kwargs_for(
        candidate,
        manifest_kwargs={"blob": code, "code_size": len(code)},
    )
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V4-boundary") == PASS
    assert verdict["verdict"] == "verified_against_stated_criteria"


def test_verdict_sha256_is_reproducible_and_excludes_produced_at() -> None:
    first = _verify(observations=_observations(_sha(_candidate())))
    second = _verify(
        now="2027-01-01T00:00:00Z",
        observations=_observations(
            _sha(_candidate()),
            started_at="2030-05-05T05:05:05Z",
        ),
    )
    assert first["produced_at"] != second["produced_at"]
    assert verdict_sha256(first) == verdict_sha256(second)


# ---------------------------------------------------------------------------
# V0 - identity failures and not_run
# ---------------------------------------------------------------------------
def test_wrong_contract_hash_rejects_in_v0() -> None:
    contract = json.loads(CONTRACT_BYTES)
    contract["binary_sha256"] = "0" * 64
    verdict = _verify(contract=contract)
    assert verdict["verdict"] == "rejected"
    assert _status(verdict, "V0-identity") == FAIL
    assert _notes_contain(verdict, "original_matches_contract")


def test_candidate_hash_not_bound_to_observations_rejects() -> None:
    verdict = _verify(observations=_wrong_binary_observations())
    assert verdict["verdict"] == "rejected"
    assert _status(verdict, "V0-identity") == FAIL
    assert _notes_contain(verdict, "candidate_matches_observations")


def _wrong_binary_observations() -> dict[str, Any]:
    observations = _observations(_sha(_candidate()))
    observations["binary"]["sha256"] = "0" * 64
    return observations


def test_observation_argv_hash_mismatch_rejects() -> None:
    def mutate(case_id: str, observed: dict[str, Any]) -> None:
        if case_id == "valid-1":
            observed["argv_sha256"] = "0" * 64

    verdict = _verify(observations=_observations(_sha(_candidate()), mutate=mutate))
    assert verdict["verdict"] == "rejected"
    assert _status(verdict, "V0-identity") == FAIL
    assert _notes_contain(verdict, "observation_argv_matches_corpus")


def test_uncovered_candidate_change_rejects() -> None:
    candidate = _candidate(extra_edits=[(0x3000, b"\x41")])
    kwargs = _kwargs_for(candidate, observations=_observations(_sha(candidate)))
    kwargs["manifest"] = _manifest(candidate)  # mutation not declared
    verdict = verify_candidate(**kwargs)
    assert verdict["verdict"] == "rejected"
    assert _status(verdict, "V0-identity") == FAIL
    assert _notes_contain(verdict, "changed_bytes_covered")


def test_section_header_change_breaks_header_identity() -> None:
    candidate = _apply_edits(
        _candidate(), [((0x3710 + 26 * 64 + 8), b"\x41")]
    )
    verdict = verify_candidate(**_kwargs_for(candidate))
    assert verdict["verdict"] == "rejected"
    assert _status(verdict, "V0-identity") == FAIL
    assert _notes_contain(verdict, "headers_byte_identical")


def test_missing_preview_hash_is_v0_not_run_and_unverified() -> None:
    candidate = _candidate()
    kwargs = _kwargs_for(
        candidate,
        manifest=_manifest(candidate, preview_sha=None),
        observations=_observations(_sha(candidate)),
    )
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V0-identity") == NOT_RUN
    assert verdict["verdict"] == "unverified"
    assert _notes_contain(verdict, "candidate_matches_manifest_preview")


# ---------------------------------------------------------------------------
# V1 - structure failures
# ---------------------------------------------------------------------------
def test_entry_point_change_rejects_in_v1() -> None:
    entry_patch = b"\x91" + ORIGINAL[25:32]
    candidate = _candidate(extra_edits=[(24, entry_patch)])
    manifest = _manifest(candidate, extra_edits=[(24, entry_patch)])
    kwargs = _kwargs_for(candidate, manifest=manifest)
    pre = verify_candidate(**kwargs)
    assert _status(pre, "V0-identity") == PASS
    assert _status(pre, "V1-structure") == FAIL
    assert pre["verdict"] == "rejected"
    assert _notes_contain(pre, "entry_unchanged")


def test_wx_segment_rejects_in_v1() -> None:
    phdr_flags_offset = 0x40 + 3 * 56 + 4
    candidate = _apply_edits(_candidate(), [(phdr_flags_offset, b"\x07")])
    verdict = verify_candidate(**_kwargs_for(candidate))
    assert verdict["verdict"] == "rejected"
    assert _status(verdict, "V1-structure") == FAIL
    assert _notes_contain(verdict, "no_wx_segments")


def test_new_dynamic_symbol_rejects_in_v1() -> None:
    candidate = _candidate(extra_edits=[(0x368, b"\x41")])
    kwargs = _kwargs_for(candidate, observations=_observations(_sha(candidate)))
    kwargs["manifest"] = _manifest(candidate, extra_edits=[(0x368, b"\x41")])
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V0-identity") == PASS
    assert _status(verdict, "V1-structure") == FAIL
    assert _notes_contain(verdict, "dynsym_section_unchanged")


def test_text_relocation_rejects_in_v1() -> None:
    relocation = struct.pack("<Q", 0x401000)
    candidate = _candidate(extra_edits=[(0x4A8, relocation)])
    kwargs = _kwargs_for(candidate, observations=_observations(_sha(candidate)))
    kwargs["manifest"] = _manifest(candidate, extra_edits=[(0x4A8, relocation)])
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V0-identity") == PASS
    assert _status(verdict, "V1-structure") == FAIL
    assert _notes_contain(verdict, "no_text_relocations")


def test_cave_outside_reserved_tail_rejects_in_v1() -> None:
    alt_cave = 0x401100
    blob = _guard_blob(cave_vaddr=alt_cave)
    patch = _patch_bytes(cave_vaddr=alt_cave)
    candidate = _candidate(blob=blob, patch_bytes=patch, cave_vaddr=alt_cave)
    kwargs = _kwargs_for(
        candidate,
        manifest_kwargs={
            "blob": blob,
            "patch_bytes": patch,
            "cave_vaddr": alt_cave,
            "code_size": GUARD_CODE_SIZE,
        },
    )
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V1-structure") == FAIL
    assert _notes_contain(verdict, "cave_inside_reserved_tail")
    assert verdict["verdict"] == "rejected"


def test_trampoline_hash_mismatch_rejects_in_v1() -> None:
    candidate = _candidate()
    manifest = _manifest(candidate)
    manifest["trampoline"]["blob_sha256"] = "0" * 64
    kwargs = _kwargs_for(candidate, manifest=manifest)
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V0-identity") == PASS
    assert _status(verdict, "V1-structure") == FAIL
    assert _notes_contain(verdict, "trampoline_hash_matches")


def test_edit_preimage_mismatch_rejects_in_v1() -> None:
    candidate = _candidate()
    manifest = _manifest(candidate)
    manifest["edits"][1]["original_bytes"] = "ff" * len(_guard_blob())
    kwargs = _kwargs_for(candidate, manifest=manifest)
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V1-structure") == FAIL
    assert _notes_contain(verdict, "edit_preimages_match_original")


# ---------------------------------------------------------------------------
# V2 / V3 - behaviour failures and not_run
# ---------------------------------------------------------------------------
def test_valid_stdout_mismatch_rejects_in_v2() -> None:
    def mutate(case_id: str, observed: dict[str, Any]) -> None:
        if case_id == "valid-5":
            observed["stdout_b64"] = base64.b64encode(b"wrong\n").decode()

    verdict = _verify(observations=_observations(_sha(_candidate()), mutate=mutate))
    assert _status(verdict, "V2-valid-behaviour") == FAIL
    assert verdict["verdict"] == "rejected"
    assert _notes_contain(verdict, "mismatch on valid-5")


def test_missing_valid_observation_is_v2_not_run_and_unverified() -> None:
    observations = _observations(_sha(_candidate()))
    observations["cases"] = [case for case in observations["cases"] if case["id"] != "valid-5"]
    verdict = _verify(observations=observations)
    assert _status(verdict, "V2-valid-behaviour") == NOT_RUN
    assert verdict["verdict"] == "unverified"
    assert _notes_contain(verdict, "no observation for valid-5")


def test_invalid_signal_rejects_in_v3() -> None:
    def mutate(case_id: str, observed: dict[str, Any]) -> None:
        if case_id == "invalid-64":
            observed.update(exit_code=-11, signal="SIGSEGV")

    verdict = _verify(observations=_observations(_sha(_candidate()), mutate=mutate))
    assert _status(verdict, "V3-invalid-response") == FAIL
    assert verdict["verdict"] == "rejected"
    assert _notes_contain(verdict, "mismatch on invalid-64")


def test_missing_invalid_observation_is_v3_not_run_and_unverified() -> None:
    observations = _observations(_sha(_candidate()))
    observations["cases"] = [
        case for case in observations["cases"] if case["id"] != "invalid-128"
    ]
    verdict = _verify(observations=observations)
    assert _status(verdict, "V3-invalid-response") == NOT_RUN
    assert verdict["verdict"] == "unverified"


# ---------------------------------------------------------------------------
# V4 - boundary
# ---------------------------------------------------------------------------
def test_missing_32_byte_case_makes_v4_not_run() -> None:
    cases = json.loads(CASES_BYTES)
    cases["cases"] = [case for case in cases["cases"] if case["id"] != "invalid-32"]
    observations = _observations(_sha(_candidate()))
    observations["cases"] = [
        case for case in observations["cases"] if case["id"] != "invalid-32"
    ]
    verdict = _verify(cases=cases, observations=observations)
    assert _status(verdict, "V4-boundary") == NOT_RUN
    assert verdict["verdict"] == "unverified"
    assert _notes_contain(verdict, "invalid boundary case not measured")


def test_unrecognised_guard_layout_makes_v4_not_run() -> None:
    blob = b"\x90" * 10 + b"\xe9" + struct.pack(
        "<i", STRCPY_PLT - (CAVE_VADDR + 10 + 5)
    )
    candidate = _candidate(blob=blob)
    kwargs = _kwargs_for(
        candidate,
        manifest_kwargs={"blob": blob, "code_size": len(blob)},
    )
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V4-boundary") == NOT_RUN
    assert verdict["verdict"] == "unverified"
    assert _notes_contain(verdict, "no comparison against the 31/32-byte boundary")


def test_compare_after_copy_jump_makes_v4_fail() -> None:
    blob = (
        b"\xe9"
        + struct.pack("<i", STRCPY_PLT - (CAVE_VADDR + 5))
        + b"\x83\xf8\x20"
    )
    candidate = _candidate(blob=blob)
    kwargs = _kwargs_for(
        candidate,
        manifest_kwargs={"blob": blob, "code_size": len(blob)},
    )
    verdict = verify_candidate(**kwargs)
    assert _status(verdict, "V4-boundary") == FAIL
    assert verdict["verdict"] == "rejected"
    assert _notes_contain(verdict, "does not precede the copy tail jump")


# ---------------------------------------------------------------------------
# V5 and the success rule
# ---------------------------------------------------------------------------
def test_v5_failure_cannot_turn_a_rejected_candidate_into_success() -> None:
    candidate = _apply_edits(ORIGINAL, [(PATCH_OFFSET, _patch_bytes())])
    kwargs = _kwargs_for(candidate, observations=_observations(_sha(candidate)))
    kwargs["manifest"] = _manifest(candidate)  # declares the cave edit too
    verdict = verify_candidate(**kwargs)
    assert _required(verdict, "V5-reapply") is False
    assert _status(verdict, "V5-reapply") == FAIL
    assert verdict["verdict"] == "rejected"
    assert _notes_contain(verdict, "optional check(s) failed")


# ---------------------------------------------------------------------------
# unsupported / error envelopes
# ---------------------------------------------------------------------------
def test_out_of_scope_manifest_is_unsupported() -> None:
    manifest = _manifest(_candidate())
    manifest["schema_version"] = 2
    verdict = _verify(manifest=manifest)
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "unsupported"
    assert all(row["status"] == NOT_RUN for row in verdict["criteria"])
    assert all(row["evidence_sha256"] is None for row in verdict["criteria"])


def test_out_of_scope_fixture_is_unsupported() -> None:
    cases = json.loads(CASES_BYTES)
    cases["fixture_id"] = "another-fixture"
    verdict = _verify(cases=cases)
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "unsupported"


def test_invalid_observations_document_is_unsupported() -> None:
    observations = _observations(_sha(_candidate()))
    del observations["environment"]
    verdict = _verify(observations=observations)
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "unsupported"


def test_internal_failure_yields_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    import pipeline.verify.verdict as verdict_module

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("synthetic verifier failure")

    monkeypatch.setattr(verdict_module, "check_identity", boom)
    verdict = _verify()
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "error"
    assert all(row["status"] == NOT_RUN for row in verdict["criteria"])
    assert _notes_contain(verdict, "RuntimeError: synthetic verifier failure")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_candidate(tmp_path: Path) -> Path:
    path = tmp_path / "candidate.elf"
    path.write_bytes(_candidate())
    return path


def _cli_args(tmp_path: Path, observations: dict[str, Any]) -> list[str]:
    candidate = _candidate()
    manifest = _manifest(candidate)
    return [
        "--contract", str(FIXTURE / "contract.json"),
        "--cases", str(FIXTURE / "cases" / "cases.json"),
        "--observations", str(_write_json(tmp_path / "observations.json", observations)),
        "--manifest", str(_write_json(tmp_path / "manifest.json", manifest)),
        "--original-elf", str(FIXTURE / "vuln.elf"),
        "--candidate-elf", str(_write_candidate(tmp_path)),
        "--now", NOW,
        "--out", str(tmp_path / "verdict.json"),
    ]


def test_cli_writes_schema_valid_verdict_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _cli_args(tmp_path, _observations(_sha(_candidate())))
    assert main(args) == 0
    verdict = json.loads((tmp_path / "verdict.json").read_text(encoding="utf-8"))
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "verified_against_stated_criteria"
    summary = json.loads(capsys.readouterr().out)
    assert summary["verdict"] == "verified_against_stated_criteria"
    assert summary["verdict_sha256"] == verdict_sha256(verdict)


def test_cli_rejected_candidate_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def mutate(case_id: str, observed: dict[str, Any]) -> None:
        if case_id == "invalid-64":
            observed.update(exit_code=-11, signal="SIGSEGV")

    args = _cli_args(
        tmp_path, _observations(_sha(_candidate()), mutate=mutate)
    )
    assert main(args) == 1
    verdict = json.loads((tmp_path / "verdict.json").read_text(encoding="utf-8"))
    _assert_schema_valid(verdict)
    assert verdict["verdict"] == "rejected"
    assert json.loads(capsys.readouterr().out)["verdict"] == "rejected"


def test_cli_missing_candidate_inputs_exits_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [
        "--contract", str(FIXTURE / "contract.json"),
        "--cases", str(FIXTURE / "cases" / "cases.json"),
        "--observations", str(FIXTURE / "observations-original.json"),
        "--out", str(tmp_path / "verdict.json"),
    ]
    assert main(args) == 2
    assert "requires --manifest" in capsys.readouterr().err


def test_cli_original_role_still_matches_g1_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "original-check.json"
    args = [
        "--role", "original",
        "--contract", str(FIXTURE / "contract.json"),
        "--cases", str(FIXTURE / "cases" / "cases.json"),
        "--observations", str(FIXTURE / "observations-original.json"),
        "--out", str(out),
    ]
    assert main(args) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["kind"] == "g1_original_check"
    assert payload["outcome"] == "observed_original"
    assert payload["binary_sha256"] == _sha(ORIGINAL)
    assert payload["cases_sha256"] == _sha(CASES_BYTES)
    assert json.loads(capsys.readouterr().out)["outcome"] == "observed_original"
