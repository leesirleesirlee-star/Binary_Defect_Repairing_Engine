"""Contract tests for the published JSON Schemas.

Every schema under `schemas/` ships with an example; the example must validate,
the closed vocabularies must stay closed, and no example may carry source
material. These tests are the enforcement behind `schemas/README.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
EXAMPLES = SCHEMAS / "examples"

PAIRS = {
    "ContractV1": "ContractV1.example.json",
    "FixtureManifestV1": "FixtureManifestV1.example.json",
    "CaseSetV1": "CaseSetV1.example.json",
    "DisassemblyViewV1": "DisassemblyViewV1.example.json",
    "FindingV1": "FindingV1.example.json",
    "FixPlanV1": "FixPlanV1.example.json",
    "AuditReportV1": "AuditReportV1.example.json",
    "ObservationV1": "ObservationV1.example.json",
    "VerdictV1": "VerdictV1.example.json",
    "EditManifestV1": "EditManifestV1.example.json",
    "CandidateV1": "CandidateV1.example.json",
}

# FixtureManifestV1 legitimately records the build source path; the other
# examples must never carry source material because they can feed a prompt.
PROMPT_FACING = (
    "ContractV1",
    "DisassemblyViewV1",
    "FixPlanV1",
    "ObservationV1",
    "VerdictV1",
    "EditManifestV1",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_for(name: str) -> dict:
    return load(SCHEMAS / f"{name}.schema.json")


def example_for(filename: str) -> dict:
    return load(EXAMPLES / filename)


def validate(name: str, payload: dict) -> list:
    return sorted(Draft202012Validator(schema_for(name)).iter_errors(payload), key=str)


@pytest.mark.parametrize("name, example", sorted(PAIRS.items()))
def test_schema_is_valid_and_example_matches(name: str, example: str) -> None:
    Draft202012Validator.check_schema(schema_for(name))
    errors = validate(name, example_for(example))
    assert not errors, [str(error) for error in errors]


@pytest.mark.parametrize("name, example", sorted(PAIRS.items()))
def test_example_carries_integer_schema_version(name: str, example: str) -> None:
    payload = example_for(example)
    assert payload["schema_version"] == 1
    assert isinstance(payload["schema_version"], int)


@pytest.mark.parametrize("name", sorted(PAIRS))
def test_every_schema_has_an_example(name: str) -> None:
    assert (EXAMPLES / PAIRS[name]).is_file()


def test_verdict_vocabulary_is_closed() -> None:
    expected = {
        "verified_against_stated_criteria",
        "rejected",
        "unverified",
        "unsupported",
        "error",
        "not_run",
    }
    assert set(schema_for("VerdictV1")["properties"]["verdict"]["enum"]) == expected


def test_second_success_label_is_rejected() -> None:
    payload = example_for("VerdictV1.example.json")
    payload["verdict"] = "success"
    assert validate("VerdictV1", payload)


def test_contract_requires_criteria_source() -> None:
    payload = example_for("ContractV1.example.json")
    del payload["criteria_source"]
    assert validate("ContractV1", payload)


def test_fix_plan_rejects_unknown_edit_kind() -> None:
    payload = example_for("FixPlanV1.example.json")
    payload["edits"][0]["kind"] = "segment-extension"
    assert validate("FixPlanV1", payload)


def test_edit_manifest_refuses_a_written_candidate() -> None:
    payload = example_for("EditManifestV1.example.json")
    payload["preview"]["candidate_written"] = True
    assert validate("EditManifestV1", payload)


def test_candidate_record_requires_a_written_candidate() -> None:
    # ADR 0004: CandidateV1 is only produced after a candidate is actually written.
    payload = example_for("CandidateV1.example.json")
    payload["candidate_written"] = False
    assert validate("CandidateV1", payload)


def test_candidate_record_requires_applied_edits_and_reversibility() -> None:
    payload = example_for("CandidateV1.example.json")
    payload["edits_applied"] = []
    assert validate("CandidateV1", payload)

    payload = example_for("CandidateV1.example.json")
    payload["reversibility"]["matches_original"] = False
    assert validate("CandidateV1", payload)


def test_candidate_record_rejects_unknown_edit_kind() -> None:
    payload = example_for("CandidateV1.example.json")
    payload["edits_applied"][0]["kind"] = "segment_extension"
    assert validate("CandidateV1", payload)


def test_candidate_record_has_no_dry_run_escape_hatch() -> None:
    # The dry-run claim lives in EditManifestV1; CandidateV1 must not carry it.
    payload = example_for("CandidateV1.example.json")
    payload["dry_run"] = False
    assert validate("CandidateV1", payload)


@pytest.mark.parametrize("name", PROMPT_FACING)
def test_prompt_facing_examples_carry_no_source_material(name: str) -> None:
    text = (EXAMPLES / PAIRS[name]).read_text(encoding="utf-8")
    assert "vuln.c" not in text
    assert "fixtures/stack-overflow-01/build" not in text


def test_manifest_requires_reserved_range() -> None:
    payload = example_for("FixtureManifestV1.example.json")
    del payload["reserved_range"]
    assert validate("FixtureManifestV1", payload)


def test_manifest_reserved_range_matches_the_rx_segment() -> None:
    payload = example_for("FixtureManifestV1.example.json")
    executable = [segment for segment in payload["segments"] if segment["flags"] == "R-X"]
    assert len(executable) == 1
    segment = executable[0]
    assert segment["filesz"] == segment["memsz"] == 0x1000
    reserved = payload["reserved_range"]
    assert int(reserved["end_vaddr"], 16) - int(reserved["start_vaddr"], 16) == reserved["size"]
    assert int(reserved["end_vaddr"], 16) == int(segment["vaddr"], 16) + segment["memsz"]


def test_case_kind_is_closed() -> None:
    payload = example_for("CaseSetV1.example.json")
    payload["cases"][0]["kind"] = "fuzz"
    assert validate("CaseSetV1", payload)


def test_expected_outcome_requires_a_shape() -> None:
    payload = example_for("CaseSetV1.example.json")
    payload["cases"][0]["expected_candidate"] = {}
    assert validate("CaseSetV1", payload)


def test_fix_plan_requires_diagnosis_and_coverage() -> None:
    for field in ("diagnosis", "stated_criteria_coverage", "stub"):
        payload = example_for("FixPlanV1.example.json")
        del payload[field]
        assert validate("FixPlanV1", payload), field


def test_audit_report_requires_exactly_three_runs() -> None:
    payload = example_for("AuditReportV1.example.json")
    payload["runs"] = payload["runs"][:2]
    assert validate("AuditReportV1", payload)


def test_finding_status_is_closed() -> None:
    payload = example_for("FindingV1.example.json")
    payload["status"] = "certain"
    assert validate("FindingV1", payload)


def test_disassembly_example_is_prompt_material_without_source() -> None:
    text = (EXAMPLES / "DisassemblyViewV1.example.json").read_text(encoding="utf-8")
    assert "vuln.c" not in text
    assert "#include" not in text
