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
    "FixPlanV1": "FixPlanV1.example.json",
    "ObservationV1": "ObservationV1.example.json",
    "VerdictV1": "VerdictV1.example.json",
    "EditManifestV1": "EditManifestV1.example.json",
}


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


@pytest.mark.parametrize("example", sorted(PAIRS.values()))
def test_examples_carry_no_source_material(example: str) -> None:
    text = (EXAMPLES / example).read_text(encoding="utf-8")
    assert "vuln.c" not in text
    assert "fixtures/stack-overflow-01/build" not in text
