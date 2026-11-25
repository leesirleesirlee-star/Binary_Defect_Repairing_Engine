"""G3 apply tests: candidate + dry-run manifest + CandidateV1."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from pipeline.repair.apply_fixplan import ApplyError, apply_fix_plan
from pipeline.repair.manifest_schema import validate_edit_manifest_v1
from pipeline.repair.self_check import check_manifest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01" / "vuln.elf"
PLAN = ROOT / "docs" / "audit" / "fix-plan-v1.json"
FIXTURE_SHA = "705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26"
# Frozen G3 evidence: applying the approved plan (run 2) to the frozen fixture
# yields exactly this candidate. A drift here is a G3 blocking defect.
CANDIDATE_SHA = "c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28"


def _apply(out: Path) -> dict:
    return apply_fix_plan(
        FIXTURE,
        PLAN,
        out,
        fixture_id="stack-overflow-01",
        now="2026-11-21T12:00:00Z",
    )


def test_selected_plan_produces_three_truthful_artifacts(tmp_path: Path) -> None:
    """G3 writes a candidate, a dry-run manifest and an applied record."""
    result = _apply(tmp_path / "artifacts")

    candidate = Path(result["candidate"])
    manifest_path = Path(result["manifest"])
    record_path = Path(result["candidate_record"])
    assert candidate.is_file()
    assert manifest_path.is_file()
    assert record_path.is_file()
    assert result["candidate_written"] is True
    assert result["fixture_unchanged"] is True
    assert result["fixture_sha256"] == FIXTURE_SHA
    assert result["self_check"] == "checks_passed"
    assert result["verdict"] is None
    assert result["executed_on_host"] is False
    assert result["candidate_sha256"] == _sha(candidate.read_bytes())
    assert result["candidate_sha256"] == CANDIDATE_SHA

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_edit_manifest_v1(manifest)
    assert manifest["dry_run"] is True
    assert manifest["preview"]["candidate_written"] is False
    assert manifest["preview"]["candidate_sha256_if_applied"] == result["candidate_sha256"]
    assert manifest["trampoline"]["code_size"] == 90
    assert manifest["trampoline"]["message_size"] == 42
    assert check_manifest(FIXTURE, manifest)["status"] == "checks_passed"

    record = json.loads(record_path.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas" / "CandidateV1.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(record)
    assert record["candidate_written"] is True
    assert record["candidate"]["sha256"] == result["candidate_sha256"]
    # ADR 0004 binding: plan/manifest hashes are file-byte hashes, not canonical JSON hashes.
    assert record["manifest"]["sha256"] == _sha(manifest_path.read_bytes())
    assert record["manifest"]["sha256"] == result["manifest_file_sha256"]
    assert record["manifest"]["sha256"] != manifest["manifest_sha256"]
    assert record["plan"]["sha256"] == _sha(PLAN.read_bytes())
    assert record["original"]["sha256"] == FIXTURE_SHA
    assert record["reversibility"]["matches_original"] is True
    assert record["plan"]["plan_id"] == "plan-c16d97ba9bc0"

    # The fixture is a read-only input: apply never mutates it.
    assert _sha(FIXTURE.read_bytes()) == FIXTURE_SHA


def test_refuses_to_overwrite_existing_artifacts(tmp_path: Path) -> None:
    """A second apply into the same directory is rejected."""
    out = tmp_path / "artifacts"
    _apply(out)
    with pytest.raises(ApplyError, match="refusing to overwrite"):
        _apply(out)


def test_refuses_wrong_original_bytes(tmp_path: Path) -> None:
    """A stale plan byte is rejected before any candidate is written."""
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["edits"][0]["original_bytes"] = "90 90 90 90 90"
    bad = tmp_path / "bad-plan.json"
    bad.write_text(json.dumps(plan), encoding="utf-8")
    out = tmp_path / "artifacts"
    with pytest.raises(ApplyError, match="original bytes"):
        apply_fix_plan(FIXTURE, bad, out)
    assert not (out / "candidate.elf").exists()


def test_guard_stub_plan_applies_like_a_code_cave(tmp_path: Path) -> None:
    """Live-audit plans use guard_stub; it must produce the same G3 candidate."""
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    for edit in plan["edits"]:
        if edit["kind"] == "code":
            edit["kind"] = "guard_stub"
    path = tmp_path / "guard-stub-plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    result = apply_fix_plan(
        FIXTURE, path, tmp_path / "artifacts", fixture_id="stack-overflow-01",
        now="2026-11-21T12:00:00Z",
    )
    assert result["candidate_written"] is True
    assert result["candidate_sha256"] == CANDIDATE_SHA


def _sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()
