"""Read-only FixPlanV1 parser for the approved G2 repair plan.

Matches the merged FixPlanV1 schema (PR #30). The plan is input evidence, not a
command to apply bytes: M5 still validates it against the frozen fixture and
contract before building any manifest. Pure standard library.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ALLOWED_TOP = {
    "schema_version",
    "plan_id",
    "fixture_id",
    "contract_sha256",
    "model",
    "diagnosis",
    "root_cause",
    "strategy",
    "edits",
    "stub",
    "valid_path",
    "invalid_path",
    "stated_criteria_coverage",
    "assumptions",
    "uncertainties",
    "verification_proposal",
}
_ALLOWED_MODEL = {"provider", "name", "prompt_sha256"}
_ALLOWED_DIAGNOSIS = {"function", "address", "instruction", "cwe", "confidence", "evidence"}
_ALLOWED_EDIT = {"kind", "address", "original_bytes", "new_bytes", "target", "reason"}
_ALLOWED_STUB = {"language", "source", "estimated_size_bytes"}
_ALLOWED_COVERAGE = {"criterion", "how"}
_ADDR = re.compile(r"^0x[0-9a-f]+$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PLAN_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_FIXTURE_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_CWE = re.compile(r"^CWE-[0-9]+$")
_HEX = re.compile(r"^[0-9a-f]*$")
_EDIT_KINDS = {"redirect_call", "code", "data", "guard_stub"}


class FixPlanError(ValueError):
    """Raised when a FixPlanV1 document is malformed or non-conforming."""


@dataclass(frozen=True)
class PlanEdit:
    """One edit from FixPlanV1."""

    kind: str
    address: int
    original_bytes: bytes
    new_bytes: bytes
    target: str | None
    reason: str | None

    @property
    def size(self) -> int:
        """Number of bytes written by this edit."""
        return len(self.new_bytes)

    @property
    def end_vaddr(self) -> int:
        """Exclusive end address."""
        return self.address + self.size

    @property
    def vaddr(self) -> int:
        """Alias for ``address``."""
        return self.address

    @property
    def bytes_hex(self) -> str:
        """Lowercase hex of the replacement bytes."""
        return self.new_bytes.hex()


@dataclass(frozen=True)
class PlanDiagnosis:
    """Diagnosis block of FixPlanV1."""

    function: str
    address: int
    instruction: str
    cwe: str
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class FixPlanView:
    """Read-only projection of FixPlanV1."""

    plan_id: str
    fixture_id: str
    contract_sha256: str
    model: Mapping[str, str]
    diagnosis: PlanDiagnosis
    root_cause: str
    strategy: str
    edits: tuple[PlanEdit, ...]
    stub: Mapping[str, Any]
    valid_path: str
    invalid_path: str
    stated_criteria_coverage: tuple[Mapping[str, str], ...]
    assumptions: tuple[str, ...]
    uncertainties: tuple[str, ...]
    verification_proposal: tuple[str, ...]

    @property
    def redirect_edits(self) -> tuple[PlanEdit, ...]:
        """Edits of kind ``redirect_call``."""
        return tuple(edit for edit in self.edits if edit.kind == "redirect_call")

    @property
    def code_edits(self) -> tuple[PlanEdit, ...]:
        """Code edits, including the guard stub."""
        return tuple(edit for edit in self.edits if edit.kind in {"code", "guard_stub"})

    @property
    def data_edits(self) -> tuple[PlanEdit, ...]:
        """Data edits."""
        return tuple(edit for edit in self.edits if edit.kind == "data")

    @property
    def edit_site_vaddr(self) -> int:
        """Redirect call site, falling back to the diagnosis address."""
        return self.redirect_edits[0].address if self.redirect_edits else self.diagnosis.address

    @property
    def cave_vaddr(self) -> int | None:
        """Guard stub address, when the plan declares one."""
        stubs = [edit for edit in self.edits if edit.kind == "guard_stub"]
        if stubs:
            return stubs[0].address
        code = [edit for edit in self.code_edits]
        return code[0].address if code else None

    @property
    def total_edit_bytes(self) -> int:
        """Sum of replacement-byte lengths."""
        return sum(edit.size for edit in self.edits)

    @property
    def edit_ranges(self) -> tuple[tuple[int, int, str], ...]:
        """Derived ``(start, end_exclusive, kind)`` ranges."""
        return tuple((edit.address, edit.end_vaddr, edit.kind) for edit in self.edits)

    @property
    def allowed_start(self) -> int:
        """Lowest edit address."""
        return min(edit.address for edit in self.edits)

    @property
    def allowed_end(self) -> int:
        """Exclusive end of the highest edit."""
        return max(edit.end_vaddr for edit in self.edits)

    @property
    def risk_assumptions(self) -> tuple[str, ...]:
        """Assumptions and uncertainties."""
        return self.assumptions + self.uncertainties

    def summary(self) -> dict[str, Any]:
        """Return a compact JSON-friendly summary."""
        return {
            "plan_id": self.plan_id,
            "fixture_id": self.fixture_id,
            "contract_sha256": self.contract_sha256,
            "function": self.diagnosis.function,
            "edit_site_vaddr": hex(self.edit_site_vaddr),
            "cave_vaddr": hex(self.cave_vaddr) if self.cave_vaddr is not None else None,
            "strategy": self.strategy,
            "edit_count": len(self.edits),
            "total_edit_bytes": self.total_edit_bytes,
            "allowed_start": hex(self.allowed_start),
            "allowed_end": hex(self.allowed_end),
            "guard_code_bytes": sum(edit.size for edit in self.code_edits),
            "guard_data_bytes": sum(edit.size for edit in self.data_edits),
            "redirect_bytes": sum(edit.size for edit in self.redirect_edits),
            "assumptions": list(self.assumptions),
            "uncertainties": list(self.uncertainties),
        }


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixPlanError(f"{name} must be an object")
    return value


def _require_fields(value: Mapping[str, Any], fields: set[str], name: str) -> None:
    missing = sorted(fields - set(value))
    if missing:
        raise FixPlanError(f"{name} missing required fields: {', '.join(missing)}")


def _reject_extra(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise FixPlanError(f"{name} has unexpected fields: {', '.join(extra)}")


def _require_str(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise FixPlanError(f"{name} must be a non-empty string")
    return value


def _require_addr(value: Any, name: str) -> int:
    if not isinstance(value, str) or not _ADDR.fullmatch(value):
        raise FixPlanError(f"{name} must be a 0x-prefixed address")
    return int(value, 16)


def _hex_bytes(value: Any, name: str) -> bytes:
    if not isinstance(value, str):
        raise FixPlanError(f"{name} must be a string")
    compact = re.sub(r"[ -]", "", value).lower()
    if not _HEX.fullmatch(compact) or len(compact) % 2:
        raise FixPlanError(f"{name} must be lowercase hex byte pairs")
    return bytes.fromhex(compact)


def _nonempty_str_list(value: Any, name: str, *, minimum: int = 0) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise FixPlanError(f"{name} must be a list with at least {minimum} item(s)")
    if not all(isinstance(item, str) and item for item in value):
        raise FixPlanError(f"{name} must contain non-empty strings")
    return tuple(value)


def _parse_edit(value: Any, index: int) -> PlanEdit:
    edit = _require_object(value, f"edits[{index}]")
    _reject_extra(edit, _ALLOWED_EDIT, f"edits[{index}]")
    _require_fields(edit, {"kind", "address", "original_bytes", "new_bytes"}, f"edits[{index}]")
    kind = edit["kind"]
    if kind not in _EDIT_KINDS:
        raise FixPlanError(f"edits[{index}].kind is not redirect_call/code/data/guard_stub")
    address = _require_addr(edit["address"], f"edits[{index}].address")
    original = _hex_bytes(edit["original_bytes"], f"edits[{index}].original_bytes")
    new = _hex_bytes(edit["new_bytes"], f"edits[{index}].new_bytes")
    target = edit.get("target")
    if target is not None and not isinstance(target, str):
        raise FixPlanError(f"edits[{index}].target must be a string")
    reason = edit.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise FixPlanError(f"edits[{index}].reason must be a string")
    return PlanEdit(
        kind=kind,
        address=address,
        original_bytes=original,
        new_bytes=new,
        target=target,
        reason=reason,
    )


def parse_fix_plan(data: Mapping[str, Any]) -> FixPlanView:
    """Parse and structurally validate a FixPlanV1 document."""
    document = _require_object(data, "FixPlanV1")
    _reject_extra(document, _ALLOWED_TOP, "FixPlanV1")
    _require_fields(document, _ALLOWED_TOP, "FixPlanV1")

    version = document["schema_version"]
    if isinstance(version, bool) or version != 1:
        raise FixPlanError("schema_version must be integer 1")
    plan_id = document["plan_id"]
    if not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
        raise FixPlanError("plan_id has an invalid format")
    fixture_id = document["fixture_id"]
    if not isinstance(fixture_id, str) or not _FIXTURE_ID.fullmatch(fixture_id):
        raise FixPlanError("fixture_id has an invalid format")
    contract_sha = document["contract_sha256"]
    if not isinstance(contract_sha, str) or not _HASH.fullmatch(contract_sha):
        raise FixPlanError("contract_sha256 must be 64 lowercase hex chars")

    model = _require_object(document["model"], "model")
    _reject_extra(model, _ALLOWED_MODEL, "model")
    _require_fields(model, _ALLOWED_MODEL, "model")
    prompt_sha = model["prompt_sha256"]
    if not isinstance(prompt_sha, str) or not _HASH.fullmatch(prompt_sha):
        raise FixPlanError("model.prompt_sha256 must be 64 lowercase hex chars")
    model_view = {
        "provider": _require_str(model["provider"], "model.provider"),
        "name": _require_str(model["name"], "model.name"),
        "prompt_sha256": prompt_sha,
    }

    diagnosis = _require_object(document["diagnosis"], "diagnosis")
    _reject_extra(diagnosis, _ALLOWED_DIAGNOSIS, "diagnosis")
    _require_fields(diagnosis, _ALLOWED_DIAGNOSIS, "diagnosis")
    function = _require_str(diagnosis["function"], "diagnosis.function")
    diagnosis_address = _require_addr(diagnosis["address"], "diagnosis.address")
    instruction = _require_str(diagnosis["instruction"], "diagnosis.instruction")
    cwe = diagnosis["cwe"]
    if not isinstance(cwe, str) or not _CWE.fullmatch(cwe):
        raise FixPlanError("diagnosis.cwe must match CWE-<number>")
    confidence = diagnosis["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise FixPlanError("diagnosis.confidence must be a number in [0, 1]")
    if not 0 <= confidence <= 1:
        raise FixPlanError("diagnosis.confidence must be a number in [0, 1]")
    evidence = _nonempty_str_list(diagnosis["evidence"], "diagnosis.evidence", minimum=1)

    raw_edits = document["edits"]
    if not isinstance(raw_edits, list) or not raw_edits:
        raise FixPlanError("edits must be a non-empty list")
    edits = tuple(_parse_edit(value, index) for index, value in enumerate(raw_edits))

    stub = _require_object(document["stub"], "stub")
    _reject_extra(stub, _ALLOWED_STUB, "stub")
    _require_fields(stub, _ALLOWED_STUB, "stub")
    if stub["language"] not in {"asm", "pseudo"}:
        raise FixPlanError("stub.language must be asm or pseudo")
    _require_str(stub["source"], "stub.source")
    estimated = stub["estimated_size_bytes"]
    if isinstance(estimated, bool) or not isinstance(estimated, int) or estimated < 0:
        raise FixPlanError("stub.estimated_size_bytes must be a non-negative integer")

    coverage_raw = document["stated_criteria_coverage"]
    if not isinstance(coverage_raw, list) or not coverage_raw:
        raise FixPlanError("stated_criteria_coverage must be a non-empty list")
    coverage: list[dict[str, str]] = []
    for index, item in enumerate(coverage_raw):
        entry = _require_object(item, f"stated_criteria_coverage[{index}]")
        _reject_extra(entry, _ALLOWED_COVERAGE, f"stated_criteria_coverage[{index}]")
        _require_fields(entry, _ALLOWED_COVERAGE, f"stated_criteria_coverage[{index}]")
        coverage.append(
            {
                "criterion": _require_str(entry["criterion"], "criterion"),
                "how": _require_str(entry["how"], "how"),
            }
        )

    return FixPlanView(
        plan_id=plan_id,
        fixture_id=fixture_id,
        contract_sha256=contract_sha,
        model=model_view,
        diagnosis=PlanDiagnosis(
            function=function,
            address=diagnosis_address,
            instruction=instruction,
            cwe=cwe,
            confidence=float(confidence),
            evidence=evidence,
        ),
        root_cause=_require_str(document["root_cause"], "root_cause"),
        strategy=_require_str(document["strategy"], "strategy"),
        edits=edits,
        stub={
            "language": stub["language"],
            "source": stub["source"],
            "estimated_size_bytes": estimated,
        },
        valid_path=_require_str(document["valid_path"], "valid_path"),
        invalid_path=_require_str(document["invalid_path"], "invalid_path"),
        stated_criteria_coverage=tuple(coverage),
        assumptions=_nonempty_str_list(document["assumptions"], "assumptions"),
        uncertainties=_nonempty_str_list(document["uncertainties"], "uncertainties"),
        verification_proposal=tuple(
            _nonempty_str_list(
                document["verification_proposal"], "verification_proposal", minimum=1
            )
        ),
    )


def validate_plan_for_fixture(
    plan: FixPlanView,
    *,
    fixture_id: str,
    edit_site_vaddr: int,
    cave_vaddr: int,
    reserved_start: int,
    reserved_end: int,
) -> None:
    """Check plan addresses against the frozen fixture bounds (pre-check only)."""
    if plan.fixture_id != fixture_id:
        raise FixPlanError(f"plan fixture_id {plan.fixture_id!r} does not match {fixture_id!r}")
    if plan.edit_site_vaddr != edit_site_vaddr:
        raise FixPlanError(
            f"plan edit_site {plan.edit_site_vaddr:#x} does not match {edit_site_vaddr:#x}"
        )
    if plan.cave_vaddr != cave_vaddr:
        raise FixPlanError(f"plan cave {plan.cave_vaddr!r} does not match {cave_vaddr:#x}")
    for edit in plan.edits:
        if edit.kind == "redirect_call":
            if edit.address != edit_site_vaddr:
                raise FixPlanError("redirect is not at the patch site")
        elif edit.address < reserved_start or edit.end_vaddr > reserved_end:
            raise FixPlanError(
                f"{edit.kind} edit {edit.address:#x}-{edit.end_vaddr:#x} "
                "is outside the reserved range"
            )
    if not plan.redirect_edits:
        raise FixPlanError("plan has no redirect_call edit")


def load_fix_plan(path: str | Path) -> FixPlanView:
    """Read a FixPlanV1 JSON file without writing or mutating it."""
    plan_path = Path(path)
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixPlanError(f"cannot read FixPlanV1: {exc}") from exc
    return parse_fix_plan(data)
