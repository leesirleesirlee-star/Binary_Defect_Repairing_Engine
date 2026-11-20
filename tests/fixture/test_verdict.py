"""Verifier tests using synthetic observations, not execution."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from pipeline.verify.verdict import decide

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01"
CONTRACT = json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))
CORPUS = json.loads((FIXTURE / "cases" / "cases.json").read_text(encoding="utf-8"))
CONTRACT["binary_sha256"] = "a" * 64


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _observations(role: str = "candidate", mutate=None):
    cases = []
    for case in CORPUS["cases"]:
        want = case["expected_candidate"] if role == "candidate" else case["expected_original"]
        observed = {
            "id": case["id"],
            "timed_out": False,
            "exit_code": want.get("exit_code"),
            "signal": want.get("signal"),
            "stdout_b64": _b64(want.get("stdout", "")),
            "stderr_b64": _b64(want.get("stderr", "")),
        }
        if mutate:
            mutate(case["id"], observed)
        cases.append(observed)
    return {"binary": {"sha256": CONTRACT["binary_sha256"]}, "cases": cases}


def test_all_candidate_cases_verified() -> None:
    verdict = decide(CONTRACT, CORPUS, _observations())
    assert verdict["outcome"] == "verified_against_stated_criteria"


def test_invalid_stderr_mismatch_rejected() -> None:
    def mutate(case_id, observed):
        if case_id == "invalid-64":
            observed["stderr_b64"] = _b64("wrong\n")

    verdict = decide(CONTRACT, CORPUS, _observations(mutate=mutate))
    assert verdict["outcome"] == "rejected"
    assert verdict["reason"] == "oracle_mismatch"


def test_missing_case_unverified() -> None:
    observations = _observations()
    observations["cases"].pop()
    assert decide(CONTRACT, CORPUS, observations)["outcome"] == "unverified"


def test_wrong_elf_rejected() -> None:
    observations = _observations()
    observations["binary"]["sha256"] = "0" * 64
    assert decide(CONTRACT, CORPUS, observations)["outcome"] == "rejected"


def test_original_crash_or_undefined_is_observed() -> None:
    def mutate(case_id, observed):
        if case_id in {"invalid-32", "invalid-33"}:
            observed["exit_code"] = 0
            observed["signal"] = None

    verdict = decide(
        CONTRACT, CORPUS, _observations(role="original", mutate=mutate), role="original"
    )
    assert verdict["outcome"] == "observed_original"
