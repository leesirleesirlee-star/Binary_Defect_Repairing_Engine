"""Build the G2 fix-plan prompt from structured, source-free inputs.

The builder accepts only ``ContractV1`` and ``DisassemblyViewV1`` dicts plus a
fixed defect description and a PoC record. It never accepts a file path or a
free-form string, and it rejects any input that carries source markers. The
assembled prompt is hashed so a changed prompt is a new version.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SYSTEM_PROMPT = _ROOT / "prompts" / "fix-plan.v1.md"
_FIXPLAN_SCHEMA = _ROOT / "schemas" / "FixPlanV1.schema.json"

# One paragraph; no source text, no source path. Frozen with the prompt version.
DEFECT_DESCRIPTION = (
    "A CWE-121 stack buffer overflow: the function `handle` copies an "
    "attacker-controlled argument into a 32-byte stack buffer with an unbounded "
    "`strcpy`, so inputs of 32 bytes or more overwrite the saved frame."
)

_SOURCE_MARKERS = (
    "vuln.c",
    "#include",
    "__attribute__",
    "static void",
    "char buf[32]",
    "fixtures/",
    "build/",
)


def load_system_prompt() -> str:
    """Return the versioned system prompt (role text only)."""
    return _SYSTEM_PROMPT.read_text(encoding="utf-8").strip()


def _assert_no_source(text: str) -> None:
    for marker in _SOURCE_MARKERS:
        if marker in text:
            raise ValueError(f"source material detected in prompt input: {marker!r}")


def build_prompt(contract: dict, view: dict, poc: dict) -> dict:
    """Return ``{"system", "user", "prompt_sha256"}`` for the model.

    ``contract`` is a ContractV1 document, ``view`` a DisassemblyViewV1 document
    and ``poc`` a ``{"input": ..., "observed_output": ...}`` record. No path or
    free-form string is accepted, so source cannot ride in.
    """
    system = load_system_prompt()
    fixplan_schema = json.loads(_FIXPLAN_SCHEMA.read_text(encoding="utf-8"))

    user_payload = {
        "defect_description": DEFECT_DESCRIPTION,
        "proof_of_concept": poc,
        "contract": {
            "stated_criteria": contract.get("stated_criteria", {}),
            "allowed_edits": contract.get("allowed_edits", {}),
            "diagnostic_hypothesis": contract.get("diagnostic_hypothesis"),
        },
        "disassembly_view": view,
        "output_schema": fixplan_schema,
        "instruction": (
            "Propose exactly one repair plan as JSON that validates against "
            "output_schema. Do not claim the binary was executed, tested or fixed."
        ),
    }
    user = json.dumps(user_payload, indent=2)

    _assert_no_source(system + user)
    prompt_sha256 = hashlib.sha256((system + "\n\n" + user).encode("utf-8")).hexdigest()
    return {"system": system, "user": user, "prompt_sha256": prompt_sha256}
