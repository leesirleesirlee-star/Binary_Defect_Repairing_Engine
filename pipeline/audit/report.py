"""Assemble and validate an ``AuditReportV1`` (issue #9)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = _ROOT / "schemas" / "AuditReportV1.schema.json"


def load_schema() -> dict:
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def build_report(
    *,
    report_id: str,
    date: str,
    fixture_sha256: str,
    contract_sha256: str,
    corpus_sha256: str,
    provider: str,
    model_name: str,
    temperature: float,
    prompt_sha256: str,
    runs: list[dict],
    selected_plan: dict,
    reviewer_scores: dict,
    correctness_established: bool,
    decision: str,
    rationale: str,
    limitations: list[str],
) -> dict:
    """Return a schema-valid ``AuditReportV1`` document.

    ``runs`` entries carry the reviewer-filled ``score`` / ``critical_errors`` /
    ``usable`` / ``notes`` alongside the harness facts.
    """
    report = {
        "schema_version": 1,
        "report_id": report_id,
        "date": date,
        "fixture_sha256": fixture_sha256,
        "contract_sha256": contract_sha256,
        "corpus_sha256": corpus_sha256,
        "model": {"provider": provider, "name": model_name, "temperature": temperature},
        "prompt_sha256": prompt_sha256,
        "runs": runs,
        "selected_plan": selected_plan,
        "reviewer_scores": reviewer_scores,
        "correctness_established": correctness_established,
        "decision": decision,
        "rationale": rationale,
        "limitations": limitations,
    }
    jsonschema.validate(report, load_schema())
    return report
