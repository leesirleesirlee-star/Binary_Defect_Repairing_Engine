"""Tests for the read-only, official FixPlanV1 consumer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.repair.fixplan_reader import (
    FixPlanError,
    load_fix_plan,
    parse_fix_plan,
    validate_plan_for_fixture,
)

EXAMPLE = Path(__file__).resolve().parents[2] / "schemas" / "examples" / "FixPlanV1.example.json"


def _example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_official_example_is_read() -> None:
    """The official example parses into the expected read-only projection."""
    view = load_fix_plan(EXAMPLE)
    assert view.plan_id == "plan-2026-11-20-run1"
    assert view.fixture_id == "stack-overflow-01"
    assert view.diagnosis.function == "handle"
    assert view.edit_site_vaddr == 0x401194
    assert view.cave_vaddr == 0x401220
    assert len(view.edits) == 2
    assert view.total_edit_bytes == 9
    assert view.allowed_start == 0x401194
    assert view.allowed_end == 0x401224
    assert view.summary()["guard_code_bytes"] == 4
    assert view.summary()["guard_data_bytes"] == 0
    assert view.summary()["redirect_bytes"] == 5
    assert len(view.stated_criteria_coverage) == 2
    assert len(view.verification_proposal) == 3
    assert len(view.risk_assumptions) == 3


def test_cave_is_derived_from_guard_stub() -> None:
    """Removing the guard_stub edit leaves no cave declaration."""
    data = _example()
    data["edits"] = [edit for edit in data["edits"] if edit["kind"] != "guard_stub"]
    view = parse_fix_plan(data)
    assert view.cave_vaddr is None


def test_rejects_extra_top_level_field() -> None:
    """The official schema is closed at the top level."""
    data = _example()
    data["schema_status"] = "draft"
    with pytest.raises(FixPlanError, match="unexpected fields"):
        parse_fix_plan(data)


def test_rejects_wrong_schema_version() -> None:
    """schema_version must be integer 1."""
    data = _example()
    data["schema_version"] = "1"
    with pytest.raises(FixPlanError, match="schema_version"):
        parse_fix_plan(data)


def test_rejects_missing_diagnosis_or_bad_kind() -> None:
    """Required diagnosis fields and the edit-kind enum are enforced."""
    data = _example()
    data["diagnosis"].pop("function")
    with pytest.raises(FixPlanError, match="diagnosis"):
        parse_fix_plan(data)

    data = _example()
    data["edits"][0]["kind"] = "segment-extension"
    with pytest.raises(FixPlanError, match="kind"):
        parse_fix_plan(data)


def test_rejects_bad_bytes_or_prompt_hash() -> None:
    """Patch bytes and prompt hash must be valid hex."""
    data = _example()
    data["edits"][0]["new_bytes"] = "GG"
    with pytest.raises(FixPlanError, match="new_bytes"):
        parse_fix_plan(data)

    data = _example()
    data["model"]["prompt_sha256"] = "not-a-hash"
    with pytest.raises(FixPlanError, match="prompt_sha256"):
        parse_fix_plan(data)


def test_validate_plan_for_fixture_accepts_official_example() -> None:
    """The example's redirect, cave and code range fit the frozen bounds."""
    view = load_fix_plan(EXAMPLE)
    validate_plan_for_fixture(
        view,
        fixture_id="stack-overflow-01",
        edit_site_vaddr=0x401194,
        cave_vaddr=0x401220,
        reserved_start=0x401211,
        reserved_end=0x402000,
    )


def test_validate_plan_rejects_wrong_fixture_or_site() -> None:
    """A plan for another fixture or a moved call site is rejected."""
    view = load_fix_plan(EXAMPLE)
    with pytest.raises(FixPlanError, match="fixture_id"):
        validate_plan_for_fixture(
            view,
            fixture_id="other",
            edit_site_vaddr=0x401194,
            cave_vaddr=0x401220,
            reserved_start=0x401211,
            reserved_end=0x402000,
        )
    data = _example()
    data["diagnosis"]["address"] = "0x401190"
    data["edits"][0]["address"] = "0x401190"
    with pytest.raises(FixPlanError, match="edit_site"):
        validate_plan_for_fixture(
            parse_fix_plan(data),
            fixture_id="stack-overflow-01",
            edit_site_vaddr=0x401194,
            cave_vaddr=0x401220,
            reserved_start=0x401211,
            reserved_end=0x402000,
        )


def test_validate_plan_rejects_out_of_range_or_missing_redirect() -> None:
    """Code/data outside the reserved range and missing redirects are errors."""
    data = _example()
    data["edits"].append(
        {
            "kind": "data",
            "address": "0x401100",
            "original_bytes": "",
            "new_bytes": "00",
        }
    )
    with pytest.raises(FixPlanError, match="outside the reserved range"):
        validate_plan_for_fixture(
            parse_fix_plan(data),
            fixture_id="stack-overflow-01",
            edit_site_vaddr=0x401194,
            cave_vaddr=0x401220,
            reserved_start=0x401211,
            reserved_end=0x402000,
        )

    data = _example()
    data["edits"] = [edit for edit in data["edits"] if edit["kind"] != "redirect_call"]
    with pytest.raises(FixPlanError, match="no redirect"):
        validate_plan_for_fixture(
            parse_fix_plan(data),
            fixture_id="stack-overflow-01",
            edit_site_vaddr=0x401194,
            cave_vaddr=0x401220,
            reserved_start=0x401211,
            reserved_end=0x402000,
        )
