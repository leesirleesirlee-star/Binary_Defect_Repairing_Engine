"""Tests for the G2 audit rubric, harness and report (issue #9)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import jsonschema
import pytest

from pipeline.ai.provider import ProviderError
from pipeline.audit import PASS_THRESHOLD, RUBRIC, TOTAL_POINTS, build_report, decide, run_audit
from pipeline.audit.canonical import canonical_plan_hash

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01" / "vuln.elf"
CONTRACT = json.loads(
    (ROOT / "fixtures" / "stack-overflow-01" / "contract.json").read_text(encoding="utf-8")
)
POC = {"input": "A" * 64, "observed_output": {"signal": "SIGSEGV"}}


def test_rubric_totals_100() -> None:
    assert TOTAL_POINTS == 100
    assert len(RUBRIC) == 7


def test_decide_rule() -> None:
    assert decide(86, [], True) == "proceed"
    assert decide(80, [], True) == "proceed"
    assert decide(74, [], True) == "iterate"
    assert decide(74, ["ignores invalid-path"], True) == "iterate"
    assert decide(90, [], False) == "change_scope"
    assert decide(40, [], True) == "change_scope"
    assert decide(None, [], False) == "change_scope"


def test_pass_threshold_is_80() -> None:
    assert PASS_THRESHOLD == 80


def _fake_plan_record(schema_valid: bool, plan: dict | None) -> dict:
    return {
        "prompt_sha256": "1" * 64,
        "response_sha256": "2" * 64,
        "model": "deepseek-chat",
        "usage": {"total_tokens": 123},
        "schema_valid": schema_valid,
        "plan": plan,
    }


def test_run_audit_keeps_three_runs() -> None:
    view = {"schema_version": 1}
    with mock.patch(
        "pipeline.audit.harness.run_plan",
        side_effect=[
            _fake_plan_record(True, {"schema_version": 1}),
            _fake_plan_record(False, None),
            _fake_plan_record(True, {"schema_version": 1}),
        ],
    ):
        records = run_audit(CONTRACT, view, POC, runs=3, api_key="x", model="deepseek-chat")
    assert [r["run_index"] for r in records] == [1, 2, 3]
    assert [r["schema_valid"] for r in records] == [True, False, True]
    assert all(r["usage"] for r in records)


def _sample_runs() -> list[dict]:
    return [
        {
            "run_index": 1,
            "schema_valid": True,
            "plan_sha256": "b" * 64,
            "score": 86,
            "critical_errors": [],
            "usable": True,
            "notes": "complete plan",
        },
        {
            "run_index": 2,
            "schema_valid": False,
            "plan_sha256": None,
            "score": None,
            "critical_errors": ["invalid JSON"],
            "usable": False,
            "notes": "kept in the table",
        },
        {
            "run_index": 3,
            "schema_valid": True,
            "plan_sha256": "c" * 64,
            "score": 74,
            "critical_errors": ["ignores the invalid-path criterion"],
            "usable": True,
            "notes": "strncpy without rejection",
        },
    ]


def test_build_report_validates() -> None:
    report = build_report(
        report_id="audit-test-01",
        date="2026-11-20",
        fixture_sha256="9f" * 32,
        contract_sha256="85" * 32,
        corpus_sha256="fa" * 32,
        provider="deepseek",
        model_name="deepseek-chat",
        temperature=0,
        prompt_sha256="1" * 64,
        runs=_sample_runs(),
        selected_plan={"run_index": 1, "plan_sha256": "b" * 64, "summary": "guard"},
        reviewer_scores={"m1": 86, "m5": 82, "resolved": 84},
        correctness_established=True,
        decision="proceed",
        rationale="covers every stated criterion",
        limitations=["one fixture, three runs"],
    )
    assert report["decision"] == "proceed"
    assert report["runs"][0]["score"] == 86


def test_build_report_rejects_bad_decision() -> None:
    with pytest.raises(jsonschema.ValidationError):
        build_report(
            report_id="audit-test-02",
            date="2026-11-20",
            fixture_sha256="9f" * 32,
            contract_sha256="85" * 32,
            corpus_sha256="fa" * 32,
            provider="deepseek",
            model_name="deepseek-chat",
            temperature=0,
            prompt_sha256="1" * 64,
            runs=_sample_runs(),
            selected_plan={"run_index": 1, "plan_sha256": "b" * 64, "summary": "guard"},
            reviewer_scores={"m1": 86, "m5": 82, "resolved": 84},
            correctness_established=True,
            decision="success",
            rationale="bad",
            limitations=["one fixture"],
        )


def test_run_audit_keeps_a_failed_run() -> None:
    view = {"schema_version": 1}
    with mock.patch(
        "pipeline.audit.harness.run_plan",
        side_effect=[
            _fake_plan_record(True, {"schema_version": 1}),
            ProviderError("provider returned HTTP 429"),
            _fake_plan_record(True, {"schema_version": 1}),
        ],
    ):
        records = run_audit(CONTRACT, view, POC, runs=3, api_key="x", model="deepseek-chat")
    assert len(records) == 3
    assert records[1]["schema_valid"] is False
    assert records[1]["plan"] is None
    assert records[1]["error"] == "provider failed: ProviderError"


def test_canonical_plan_hash_matches_the_frozen_plan() -> None:
    plan = json.loads((ROOT / "docs" / "audit" / "fix-plan-v1.json").read_text(encoding="utf-8"))
    expected = "6f5f3535f3103acd04665aa4e19a2e8b6075ab7f8bc9657f5f53f01a2693ae1a"
    assert canonical_plan_hash(plan) == expected


def test_canonical_plan_hash_is_independent_of_formatting() -> None:
    plan = {"b": 1, "a": [1, 2]}
    reordered = {"a": [1, 2], "b": 1}
    assert canonical_plan_hash(plan) == canonical_plan_hash(reordered)
    assert canonical_plan_hash(plan) != canonical_plan_hash({"a": [1, 2], "b": 2})


def test_summary_out_writes_machine_readable_summary(tmp_path) -> None:
    from pipeline.audit import __main__ as audit_main

    fake_records = [
        {
            "run_index": 1,
            "schema_valid": True,
            "plan_sha256": "a" * 64,
            "plan": {"schema_version": 1},
            "model": "deepseek-chat",
            "usage": {"total_tokens": 100},
            "prompt_sha256": "b" * 64,
            "raw": "{}",
            "error": None,
        }
    ]
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(audit_main, "run_audit", lambda *a, **k: fake_records)
    try:
        fixture = ROOT / "fixtures" / "stack-overflow-01"
        summary_out = tmp_path / "summary.json"
        raw_dir = tmp_path / "raw"
        rc = audit_main.main(
            [
                "--fixture-dir",
                str(fixture),
                "--raw-dir",
                str(raw_dir),
                "--summary-out",
                str(summary_out),
                "--model",
                "deepseek-chat",
            ]
        )
    finally:
        monkeypatch.undo()
    assert rc == 0
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    expected_contract = hashlib.sha256((fixture / "contract.json").read_bytes()).hexdigest()
    assert summary["model"] == "deepseek-chat"
    assert summary["contract_sha256"] == expected_contract
    assert summary["prompt_sha256"] == "b" * 64
    assert summary["runs"][0]["plan_sha256"] == "a" * 64
    assert summary["runs"][0]["plan"] == {"schema_version": 1}
    assert (raw_dir / "run-1.json").is_file()
