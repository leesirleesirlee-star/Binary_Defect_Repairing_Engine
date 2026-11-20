#!/usr/bin/env python3
"""Turn guest observations into a deterministic verdict.

Only this module writes verdict.json. It accepts only the frozen contract and
the observations; it does not read AI output and does not execute the ELF.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def decide(contract: dict, observations: dict) -> dict:
    if observations.get("elf_sha256") != contract.get("binary_sha256"):
        return {"outcome": "rejected", "reason": "elf_sha256_mismatch"}
    expected_cases = {case["path"]: case for case in contract["cases"]}
    observed_cases = {case["path"]: case for case in observations.get("cases", [])}
    if set(expected_cases) != set(observed_cases):
        return {"outcome": "unverified", "reason": "case_set_mismatch"}
    failures = []
    for path, expected in expected_cases.items():
        observed = observed_cases[path]
        expect = expected["expect"]
        if observed.get("timed_out"):
            failures.append({"path": path, "reason": "timeout"})
            continue
        if "exit_code" in expect and observed.get("exit_code") != expect["exit_code"]:
            failures.append({"path": path, "reason": "exit_code"})
        if "signal" in expect and observed.get("signal") != expect["signal"]:
            failures.append({"path": path, "reason": "signal"})
    if failures:
        return {"outcome": "rejected", "reason": "oracle_mismatch", "failures": failures}
    return {"outcome": "verified_against_stated_criteria", "reason": "all_cases_match"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    observations = json.loads(args.observations.read_text(encoding="utf-8"))
    verdict = decide(contract, observations)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdict))
    return 0 if verdict["outcome"] == "verified_against_stated_criteria" else 1


if __name__ == "__main__":
    raise SystemExit(main())
