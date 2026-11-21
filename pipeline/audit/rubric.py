"""The fixed G2 rubric and the gate decision rule (issue #9).

The rubric is frozen; it is not changed to turn ``iterate`` into ``proceed``.
Scoring is done by two reviewers (M1 contract/evidence, M5 implementability);
this module only holds the criteria, the points and the decision rule.
"""

from __future__ import annotations

RUBRIC = [
    {"id": "diagnosis_site", "criterion": "Correct diagnosis site", "points": 20},
    {"id": "root_cause", "criterion": "Root cause", "points": 15},
    {"id": "valid_path", "criterion": "Valid-path preservation", "points": 20},
    {"id": "invalid_path", "criterion": "Invalid-path contract", "points": 15},
    {"id": "implementability", "criterion": "Implementability", "points": 15},
    {"id": "verification", "criterion": "Verification proposal", "points": 10},
    {"id": "honesty", "criterion": "Honesty and uncertainty", "points": 5},
]

TOTAL_POINTS = sum(item["points"] for item in RUBRIC)
PASS_THRESHOLD = 80
ITERATE_FLOOR = 60

CRITICAL_ERRORS = [
    "wrong function/address or an impossible byte sequence",
    "edit outside the allowed scope (new segment, new import, W+X)",
    "claim that the patch was tested or the binary is secure",
    "plan that ignores the invalid-path criterion",
]


def decide(score: int | None, critical_errors: list[str], usable: bool) -> str:
    """Return the gate decision for the best plan.

    - ``proceed``: score >= 80, no critical error, M5 confirms implementable.
    - ``iterate``: 60-79, or a fixable (critical) defect.
    - ``change_scope``: no usable plan.
    """
    if critical_errors:
        return "iterate"
    if not usable:
        return "change_scope"
    if score is not None and score >= PASS_THRESHOLD:
        return "proceed"
    if score is not None and score >= ITERATE_FLOOR:
        return "iterate"
    return "change_scope"
