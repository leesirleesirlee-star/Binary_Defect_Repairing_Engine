"""Tests for the G2 audit rubric, harness and report (issue #9)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import jsonschema
import pytest

from pipeline.ai.provider import ProviderError
from pipeline.audit import PASS_THRESHOLD, RUBRIC, TOTAL_POINTS, build_report, decide, run_audit

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
