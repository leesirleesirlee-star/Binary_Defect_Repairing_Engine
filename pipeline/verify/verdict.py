#!/usr/bin/env python3
"""Deterministic verifier for MVP2 fixture observations.

Only this module writes verdict.json. It reads the frozen contract, the frozen
case list, and guest observations; it never reads AI output and never executes
the ELF.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def _decoded(value: str) -> bytes:
    return base64.b64decode(value)


def decide(contract: dict, corpus: dict, observations: dict, role: str = "candidate") -> dict:
    if observations.get("binary", {}).get("sha256") != contract.get("binary_sha256"):
        return {"outcome": "rejected", "reason": "binary_sha256_mismatch"}
    expected = {case["id"]: case for case in corpus["cases"]}
    observed = {case["id"]: case for case in observations.get("cases", [])}
    if set(expected) != set(observed):
        return {"outcome": "unverified", "reason": "case_set_mismatch"}
    failures = []
    for case_id, case in expected.items():
        got = observed[case_id]
        if got.get("timed_out"):
            failures.append({"case": case_id, "reason": "timeout"})
            continue
        want = case["expected_candidate"] if role == "candidate" else case["expected_original"]
        if role == "original" and want.get("crash_or_undefined"):
            continue
        if "exit_code" in want and got.get("exit_code") != want["exit_code"]:
            failures.append({"case": case_id, "reason": "exit_code"})
        if "signal" in want and got.get("signal") != want["signal"]:
            failures.append({"case": case_id, "reason": "signal"})
        if "stdout" in want and _decoded(got.get("stdout_b64", "")) != want["stdout"].encode():
            failures.append({"case": case_id, "reason": "stdout"})
        if "stderr" in want and _decoded(got.get("stderr_b64", "")) != want["stderr"].encode():
            failures.append({"case": case_id, "reason": "stderr"})
    if failures:
        return {"outcome": "rejected", "reason": "oracle_mismatch", "failures": failures}
    outcome = "verified_against_stated_criteria" if role == "candidate" else "observed_original"
    return {"outcome": outcome, "reason": "all_cases_match"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--role", choices=("original", "candidate"), default="candidate")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    corpus = json.loads(args.cases.read_text(encoding="utf-8"))
    observations = json.loads(args.observations.read_text(encoding="utf-8"))
    verdict = decide(contract, corpus, observations, args.role)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdict))
    return 0 if verdict["outcome"] in {"verified_against_stated_criteria", "observed_original"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
