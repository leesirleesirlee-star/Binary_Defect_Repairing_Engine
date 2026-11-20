"""Minimal honesty-preserving presentation helpers.

These helpers render values that came from persisted JSON.  They never infer a
result: a missing value is shown as ``missing`` and a verdict is shown only when
the persisted document contains one.  The four full screens belong to #12; this
module gives their shared honesty boundary a tested home.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

MISSING = "missing"
SUCCESS_OUTCOME = "verified_against_stated_criteria"


def _text(value: Any) -> str:
    if value is None:
        return MISSING
    return escape(str(value), quote=True)


def render_observation(observation: Any) -> str:
    """Render one observation's status verbatim; absent status is ``missing``."""
    if not isinstance(observation, Mapping):
        return MISSING
    if "status" not in observation or observation.get("status") is None:
        return MISSING
    return _text(observation.get("status"))


def render_artifact(artifact: Any) -> str:
    """Render an artifact reference; missing or unbound artifacts are ``missing``."""
    if artifact is None:
        return MISSING
    if isinstance(artifact, Mapping):
        if artifact.get("missing") is True or artifact.get("exists") is False:
            return MISSING
        if artifact.get("present") is False:
            return MISSING
        for key in ("path", "artifact_id", "name", "sha256"):
            if artifact.get(key) not in (None, ""):
                return _text(artifact[key])
        return MISSING
    if isinstance(artifact, str) and artifact.strip():
        return _text(artifact)
    return MISSING


def render_verdict(verdict: Any) -> str:
    """Render only the outcome stored in a verdict document.

    The absence of a verdict is rendered as ``missing``; observations alone can
    never produce :data:`SUCCESS_OUTCOME`.
    """
    if not isinstance(verdict, Mapping):
        return MISSING
    outcome = verdict.get("outcome")
    if outcome in (None, ""):
        return MISSING
    return _text(outcome)


def render_artifact_list(artifacts: Any) -> list[str]:
    """Render a sequence of artifact references without inventing presence."""
    if artifacts is None:
        return [MISSING]
    if isinstance(artifacts, (str, bytes)) or not isinstance(artifacts, Sequence):
        return [MISSING]
    if not artifacts:
        return [MISSING]
    return [render_artifact(item) for item in artifacts]


def render_verification(document: Mapping[str, Any]) -> str:
    """Render the verification fragment used by the honesty tests.

    This is intentionally a fragment, not the #12 screen.  It exposes the
    verdict and observations so tests can prove that a passing observation
    alone never becomes the success label.
    """
    verdict = render_verdict(document.get("verdict"))
    observations = document.get("observations")
    if observations is None:
        statuses: list[str] = [MISSING]
    elif isinstance(observations, Sequence) and not isinstance(observations, (str, bytes)):
        statuses = [render_observation(item) for item in observations] or [MISSING]
    else:
        statuses = [MISSING]
    artifacts = render_artifact_list(document.get("artifacts"))
    return (
        "<section class=\"verification-fragment\">"
        f"<p class=\"verdict\" data-outcome=\"{verdict}\">verdict: {verdict}</p>"
        f"<ul class=\"observations\">{''.join(f'<li>{status}</li>' for status in statuses)}</ul>"
        f"<ul class=\"artifacts\">{''.join(f'<li>{item}</li>' for item in artifacts)}</ul>"
        "</section>"
    )
