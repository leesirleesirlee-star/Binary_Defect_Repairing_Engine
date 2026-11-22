#!/usr/bin/env python3
"""Deterministic V0-V5 verifier and the only writer of a ``VerdictV1``.

This module reads the frozen contract, the frozen case list, the guest
observations, the ``EditManifestV1`` and the original/candidate ELF bytes.  It
never executes an ELF, never reads the AI plan and never imports
``pipeline.ai``, ``pipeline.audit`` or ``pipeline.repair``.

Verdict rules (``docs/plan/03-fixture-and-ai-audit-spec.md`` section 8):

* ``verified_against_stated_criteria`` only when every required check (V0-V4)
  passes on matching original/candidate/manifest/observation hashes;
* ``rejected`` when a required check fails;
* ``unverified`` when a required check is ``not_run`` or the hashes do not bind;
* ``unsupported`` when an input is outside the declared MVP2 scope;
* ``error`` when the verifier itself fails before a verdict exists;
* ``not_run`` is an individual check state, never a success.

Determinism: the verdict body is canonical JSON; ``produced_at`` is excluded
from the reproducible ``verdict_sha256`` printed on stdout, so two runs on the
same inputs yield the same hash (``--now`` pins the timestamp for tests).
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pipeline.verify.canonical import (
    CRITERIA,
    FAIL,
    NOT_RUN,
    OPTIONAL_LIMITATION,
    PASS,
    SCOPE_LIMITATION,
    STATIC_LIMITATION,
    VERDICT_VOCABULARY,
    VERIFIED,
    digest,
    evidence_row,
    sha256_hex,
    utc_now,
    verdict_sha256,
)
from pipeline.verify.checks import (
    Inputs,
    UnsupportedInput,
    VerifierError,
    check_boundary,
    check_identity,
    check_invalid,
    check_reapply,
    check_structure,
    check_valid,
    compute_coverage,
    observed_case_map,
    parse_candidate,
    parse_original,
    validate_inputs,
)

PRODUCED_BY = "pipeline.verify.verdict"
_SUCCESS_OUTCOMES = frozenset({VERIFIED, "observed_original"})
_VERDICT_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "VerdictV1.schema.json"


# ---------------------------------------------------------------------------
# Legacy G1 original-binary comparison (kept for ``--role original``)
# ---------------------------------------------------------------------------
def _decoded(value: str) -> bytes:
    return base64.b64decode(value)


def decide(
    contract: dict, corpus: dict, observations: dict, role: str = "candidate"
) -> dict:
    """Compare observations with the corpus expectations (G1 original check)."""
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


# ---------------------------------------------------------------------------
# Verdict construction
# ---------------------------------------------------------------------------
def _decide(rows: list[dict[str, Any]], *, bound: bool) -> str:
    """Return the verdict label from required-check statuses and hash binding."""
    required = [row for row in rows if row["required"]]
    if any(row["status"] == FAIL for row in required):
        return "rejected"
    if any(row["status"] != PASS for row in required):
        return "unverified"
    if not bound:
        return "unverified"
    return VERIFIED


def _base_limitations(rows: list[dict[str, Any]], notes: list[str]) -> list[str]:
    """Assemble the deterministic limitations list in a fixed order."""
    limitations = [SCOPE_LIMITATION, OPTIONAL_LIMITATION, STATIC_LIMITATION]
    limitations.extend(notes)
    optional_failed = [
        row["id"] for row in rows if not row["required"] and row["status"] == FAIL
    ]
    if optional_failed:
        limitations.append(
            "optional check(s) failed: " + ", ".join(optional_failed)
        )
    return limitations


def _run_checks(inputs: Inputs, now: str | None) -> dict[str, Any]:
    """Run V0-V5 and build the schema-shaped VerdictV1; never label success alone."""
    validate_inputs(inputs)
    original = parse_original(inputs.original_bytes)
    candidate, candidate_error = parse_candidate(inputs.candidate_bytes)
    observed, duplicate_ids = observed_case_map(inputs.observations)

    rows: list[dict[str, Any]] = []
    notes: list[str] = []
    row, identity_notes, bound = check_identity(
        inputs, original, candidate, observed, duplicate_ids
    )
    rows.append(row)
    notes.extend(identity_notes)
    row, structure_notes = check_structure(inputs, original, candidate, candidate_error)
    rows.append(row)
    notes.extend(structure_notes)
    row, valid_notes = check_valid(inputs, observed)
    rows.append(row)
    notes.extend(valid_notes)
    row, invalid_notes = check_invalid(inputs, observed)
    rows.append(row)
    notes.extend(invalid_notes)
    row, boundary_notes = check_boundary(
        inputs, candidate, candidate_error, observed
    )
    rows.append(row)
    notes.extend(boundary_notes)
    candidate_sha = sha256_hex(inputs.candidate_bytes)
    row, reapply_notes = check_reapply(inputs, candidate_sha)
    rows.append(row)
    notes.extend(reapply_notes)

    verdict = _decide(rows, bound=bound)
    if verdict == VERIFIED and not (
        bound
        and all(row["status"] == PASS for row in rows if row["required"])
    ):
        raise VerifierError("refusing success without bound hashes and passing checks")
    return {
        "schema_version": 1,
        "verdict": verdict,
        "original_sha256": sha256_hex(inputs.original_bytes),
        "candidate_sha256": candidate_sha,
        "contract_sha256": inputs.contract_sha256,
        "criteria": rows,
        "coverage": compute_coverage(inputs.cases, observed, rows),
        "limitations": _base_limitations(rows, notes),
        "produced_at": now or utc_now(),
        "produced_by": PRODUCED_BY,
    }


def _not_computed(
    inputs: Inputs,
    original_sha: str,
    candidate_sha: str,
    outcome: str,
    reason: str,
    now: str | None,
) -> dict[str, Any]:
    """Build an unsupported/error envelope with every criterion explicitly not_run."""
    rows = [evidence_row(criterion_id, required, NOT_RUN) for criterion_id, required in CRITERIA]
    return {
        "schema_version": 1,
        "verdict": outcome,
        "original_sha256": original_sha,
        "candidate_sha256": candidate_sha,
        "contract_sha256": inputs.contract_sha256,
        "criteria": rows,
        "coverage": {
            "cases_total": _case_count(inputs.cases),
            "cases_run": 0,
            "unmeasured": [criterion_id for criterion_id, _ in CRITERIA],
        },
        "limitations": [SCOPE_LIMITATION, f"{outcome}: {reason}"],
        "produced_at": now or utc_now(),
        "produced_by": PRODUCED_BY,
    }


def _case_count(cases: Any) -> int:
    """Return the corpus case count when the document is usable, else 0."""
    if not isinstance(cases, dict):
        return 0
    items = cases.get("cases")
    return len(items) if isinstance(items, list) else 0


def validate_verdict(verdict: dict[str, Any]) -> None:
    """Enforce the success rule and the frozen VerdictV1 schema before writing."""
    if verdict.get("verdict") not in VERDICT_VOCABULARY:
        raise VerifierError(f"verdict {verdict.get('verdict')!r} is outside the vocabulary")
    if verdict.get("verdict") == VERIFIED:
        required = [row for row in verdict.get("criteria", []) if row.get("required")]
        if not required or any(row.get("status") != PASS for row in required):
            raise VerifierError(
                "refusing to write success without every required check passing"
            )
    schema = json.loads(_VERDICT_SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(verdict), key=str)
    if errors:
        raise VerifierError(f"VerdictV1 schema validation failed: {errors[0].message}")


def verify_candidate(
    *,
    contract: dict[str, Any],
    cases: dict[str, Any],
    observations: dict[str, Any],
    manifest: dict[str, Any],
    original_bytes: bytes,
    candidate_bytes: bytes,
    contract_sha256: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Verify one candidate and return a schema-valid VerdictV1 object."""
    inputs = Inputs(
        contract=contract,
        cases=cases,
        observations=observations,
        manifest=manifest,
        original_bytes=original_bytes,
        candidate_bytes=candidate_bytes,
        contract_sha256=contract_sha256 or digest(contract),
    )
    original_sha = sha256_hex(original_bytes)
    candidate_sha = sha256_hex(candidate_bytes)
    try:
        verdict = _run_checks(inputs, now)
    except UnsupportedInput as exc:
        verdict = _not_computed(
            inputs, original_sha, candidate_sha, "unsupported", str(exc), now
        )
    except Exception as exc:  # noqa: BLE001 - the verdict envelope must never leak
        verdict = _not_computed(
            inputs,
            original_sha,
            candidate_sha,
            "error",
            f"{type(exc).__name__}: {exc}",
            now,
        )
    validate_verdict(verdict)
    return verdict


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class _CliError(Exception):
    """A file could not be read or decoded before verification could start."""


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _CliError(f"cannot read {label} {path}: {exc}") from exc


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = _read_bytes(path, label)
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _CliError(f"{label} {path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise _CliError(f"{label} {path} must contain a JSON object")
    return document, raw


def _write_json(payload: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _original_check(
    args: argparse.Namespace,
    contract: dict[str, Any],
    cases: dict[str, Any],
    observations: dict[str, Any],
    cases_raw: bytes,
) -> int:
    result = decide(contract, cases, observations, role="original")
    payload = {
        "schema_version": 1,
        "kind": "g1_original_check",
        "binary_sha256": observations.get("binary", {}).get("sha256"),
        "cases_sha256": sha256_hex(cases_raw),
        **result,
    }
    _write_json(payload, args.out)
    print(json.dumps(payload, sort_keys=True))
    return 0 if result["outcome"] in _SUCCESS_OUTCOMES else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic V0-V5 verifier and VerdictV1 writer"
    )
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--role", choices=("original", "candidate"), default="candidate")
    parser.add_argument("--manifest", type=Path, help="EditManifestV1 (candidate role)")
    parser.add_argument("--original-elf", type=Path, help="original ELF bytes")
    parser.add_argument("--candidate-elf", type=Path, help="candidate ELF bytes")
    parser.add_argument(
        "--now",
        help="fixed ISO-8601 produced_at timestamp for reproducible verdict hashes",
    )
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; returns 0 only for a passing verdict or G1 original check."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    verdict: dict[str, Any] = {}
    try:
        contract, contract_raw = _read_json(args.contract, "contract")
        cases, cases_raw = _read_json(args.cases, "cases")
        observations, _ = _read_json(args.observations, "observations")
        if args.role == "original":
            return _original_check(args, contract, cases, observations, cases_raw)
        missing = [
            flag
            for flag, value in (
                ("--manifest", args.manifest),
                ("--original-elf", args.original_elf),
                ("--candidate-elf", args.candidate_elf),
            )
            if value is None
        ]
        if missing:
            raise _CliError("--role candidate requires " + ", ".join(missing))
        manifest, _ = _read_json(args.manifest, "manifest")
        original_bytes = _read_bytes(args.original_elf, "original ELF")
        candidate_bytes = _read_bytes(args.candidate_elf, "candidate ELF")
        verdict = verify_candidate(
            contract=contract,
            cases=cases,
            observations=observations,
            manifest=manifest,
            original_bytes=original_bytes,
            candidate_bytes=candidate_bytes,
            contract_sha256=sha256_hex(contract_raw),
            now=args.now,
        )
        _write_json(verdict, args.out)
    except _CliError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    except OSError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2
    summary = {
        "verdict": verdict["verdict"],
        "verdict_sha256": verdict_sha256(verdict),
        "out": str(args.out),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if verdict["verdict"] == VERIFIED else 1


if __name__ == "__main__":
    raise SystemExit(main())
