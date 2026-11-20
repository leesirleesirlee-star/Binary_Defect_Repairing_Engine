"""Verifier decision tests; these use synthetic observations, not execution."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.verify.verdict import decide

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads(
    (ROOT / "fixtures" / "stack-overflow-01" / "contract.json").read_text(encoding="utf-8")
)


def _observations(mutate=None):
    cases = []
    for case in CONTRACT["cases"]:
        observed = {
            "path": case["path"],
            "kind": case["kind"],
            "timed_out": False,
            "exit_code": 0 if case["kind"] == "valid" else -11,
            "signal": None if case["kind"] == "valid" else "SIGSEGV",
        }
        if mutate:
            mutate(observed)
        cases.append(observed)
    return {"elf_sha256": CONTRACT["binary_sha256"], "cases": cases}


def test_all_cases_match_verified() -> None:
    assert decide(CONTRACT, _observations()) == {
        "outcome": "verified_against_stated_criteria",
        "reason": "all_cases_match",
    }


def test_signal_mismatch_rejected() -> None:
    def mutate(observed):
        if observed["kind"] == "invalid":
            observed["signal"] = "SIGABRT"
            observed["exit_code"] = -6

    verdict = decide(CONTRACT, _observations(mutate))
    assert verdict["outcome"] == "rejected"
    assert verdict["reason"] == "oracle_mismatch"


def test_missing_case_unverified() -> None:
    observations = _observations()
    observations["cases"].pop()
    assert decide(CONTRACT, observations)["outcome"] == "unverified"


def test_wrong_elf_rejected() -> None:
    observations = _observations()
    observations["elf_sha256"] = "0" * 64
    assert decide(CONTRACT, observations)["outcome"] == "rejected"
