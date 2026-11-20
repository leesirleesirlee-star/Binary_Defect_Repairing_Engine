"""Honesty tests: missing is missing and success needs a persisted verdict."""

from __future__ import annotations

from app.render import (
    MISSING,
    SUCCESS_OUTCOME,
    render_artifact,
    render_artifact_list,
    render_observation,
    render_verdict,
    render_verification,
)


def test_not_run_is_rendered_verbatim() -> None:
    assert render_observation({"status": "not_run"}) == "not_run"
    html = render_verification(
        {"observations": [{"status": "not_run"}], "verdict": {"outcome": "not_run"}}
    )
    assert "not_run" in html
    assert "passed" not in html


def test_unsupported_is_rendered_verbatim() -> None:
    assert render_observation({"status": "unsupported"}) == "unsupported"


def test_missing_observation_is_missing_not_passing() -> None:
    assert render_observation({}) == MISSING
    assert render_observation(None) == MISSING


def test_missing_artifact_is_missing_not_success() -> None:
    assert render_artifact(None) == MISSING
    assert (
        render_artifact({"path": "fixtures/stack-overflow-01/vuln.elf", "exists": False})
        == MISSING
    )
    assert render_artifact({"missing": True}) == MISSING
    assert render_artifact({}) == MISSING


def test_artifact_reference_renders_only_persisted_identity() -> None:
    assert render_artifact({"path": "fixtures/stack-overflow-01/vuln.elf"}) == (
        "fixtures/stack-overflow-01/vuln.elf"
    )
    assert render_artifact_list([]) == [MISSING]
    assert render_artifact_list(None) == [MISSING]


def test_no_success_label_without_a_verdict() -> None:
    html = render_verification(
        {
            "observations": [{"status": "passed"}, {"status": "not_run"}],
            "artifacts": [{"path": "candidate.elf"}],
        }
    )
    assert SUCCESS_OUTCOME not in html
    assert "verdict: missing" in html


def test_success_label_comes_only_from_a_persisted_verdict() -> None:
    verdict = {"outcome": SUCCESS_OUTCOME}
    assert render_verdict(verdict) == SUCCESS_OUTCOME
    html = render_verification({"verdict": verdict, "observations": []})
    assert SUCCESS_OUTCOME in html


def test_verdict_without_outcome_is_missing() -> None:
    assert render_verdict({}) == MISSING
    assert render_verdict(None) == MISSING
