"""Local task runner: execute the pipeline for one GUI task and append journal events.

Contract: `docs/interfaces/gui-events-v1.md` (H11), decision ADR 0003.

The runner executes pipeline CLIs as subprocesses and writes
`var/events/{task_id}.jsonl`. It never imports GUI code or pipeline code, never
reads a provider key, never executes an ELF, and never fabricates a verdict,
score or success label.

`repair` runs M5's apply CLI on the approved `FixPlanV1`; `verify` runs M3's
verifier only when the guest wrote `observations-candidate.json` and records the
persisted verdict verbatim. `audit`, `decision` and `export` stay `skipped` with
stable codes, so the terminal `run_end` is `failed` — never `completed`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

STEPS = ("collect", "freeze", "analyze", "audit", "decision", "repair", "verify", "export")
_TASK_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
_MAX_EVENT_BYTES = 1_000_000
_ANALYZE_TIMEOUT_S = 120
_REPAIR_TIMEOUT_S = 120
_VERIFY_TIMEOUT_S = 300
_OBSERVATIONS_FILE = "observations-candidate.json"
_VERDICT_FILE = "verdict.json"
_DEFAULT_PLAN = "docs/audit/fix-plan-v1.json"
_VERIFIED = "verified_against_stated_criteria"
#: The frozen six-word VerdictV1 vocabulary; the runner adds and infers nothing.
_VERDICT_VOCABULARY = frozenset(
    {_VERIFIED, "rejected", "unverified", "unsupported", "error", "not_run"}
)

EXIT_OK = 0
EXIT_INVALID = 2
EXIT_NOT_APPROVED = 3
EXIT_INTERNAL = 4


class RunnerError(Exception):
    """A task cannot be run; carries the process exit code."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


class StageOutcome(NamedTuple):
    """What one pipeline stage actually produced: reason code, files, evaluation id."""

    reason: str | None = None
    files: int = 0
    evaluation_id: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RunnerError(f"{path} must contain a JSON object", EXIT_INVALID)
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _read_json_text(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _valid_task_id(task_id: str) -> bool:
    return 1 <= len(task_id) <= 128 and set(task_id) <= _TASK_ID_CHARS


def load_task(var_root: Path, task_id: str) -> dict[str, Any]:
    """Load and shape-check the GUI-written task snapshot."""
    if not _valid_task_id(task_id):
        raise RunnerError(f"invalid task id: {task_id!r}", EXIT_INVALID)
    path = var_root / "tasks" / f"{task_id}.json"
    if not path.is_file():
        raise RunnerError(f"task not found: {task_id}", EXIT_INVALID)
    task = _read_json(path)
    for field in (
        "id",
        "fixture_id",
        "binary",
        "corpus",
        "contract_sha256",
        "review_binding_digest",
    ):
        if field not in task:
            raise RunnerError(f"task is missing {field}", EXIT_INVALID)
    if task["id"] != task_id:
        raise RunnerError("task id does not match its file name", EXIT_INVALID)
    override = task.get("plan")
    if override is not None and (not isinstance(override, str) or not override.strip()):
        raise RunnerError("task.plan must be a non-empty relative path", EXIT_INVALID)
    return task


def check_approval(task: dict[str, Any]) -> None:
    """Refuse to run an unapproved task or a stale content binding."""
    approval = task.get("approval") or {}
    if not approval.get("approved"):
        raise RunnerError("task is not approved", EXIT_NOT_APPROVED)
    if approval.get("binding_digest") != task["review_binding_digest"]:
        raise RunnerError("approval is stale: binding digest changed", EXIT_NOT_APPROVED)


def resolve_binary(repo_root: Path, task: dict[str, Any]) -> Path:
    """Return the frozen fixture binary path and verify it matches the task."""
    binary = task.get("binary") or {}
    relative = binary.get("path")
    expected = binary.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise RunnerError("task.binary must carry path and sha256", EXIT_INVALID)
    path = repo_root / "fixtures" / str(task["fixture_id"]) / relative
    if not path.is_file():
        raise RunnerError(f"fixture binary is missing: {relative}", EXIT_INVALID)
    actual = _sha256_file(path)
    if actual != expected:
        raise RunnerError(
            f"fixture binary does not match the approved task ({actual[:12]} != {expected[:12]})",
            EXIT_INVALID,
        )
    return path


def resolve_plan(repo_root: Path, task: dict[str, Any]) -> Path:
    """Resolve the approved FixPlanV1: task override, else the G2-selected plan."""
    path = Path(str(task.get("plan") or _DEFAULT_PLAN))
    root = repo_root.resolve()
    resolved = (root / path).resolve()
    if path.is_absolute() or root not in resolved.parents:
        raise RunnerError("task.plan must be a relative path inside the repo", EXIT_INVALID)
    return resolved


class Journal:
    """Append-only writer for `var/events/{task_id}.jsonl` (gui-events-v1)."""

    def __init__(self, var_root: Path, task_id: str, run_id: str) -> None:
        self.path = var_root / "events" / f"{task_id}.jsonl"
        self.task_id = task_id
        self.run_id = run_id
        self.seq = self._last_seq()
        self.events = 0

    def _last_seq(self) -> int:
        if not self.path.is_file():
            return 0
        last = 0
        for raw in self.path.read_bytes().splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            last = max(last, int(record.get("seq", 0)))
        return last

    def append(
        self, event_type: str, payload: dict[str, Any], *, step_id: str | None = None
    ) -> None:
        self.seq += 1
        record = {
            "version": 1,
            "type": event_type,
            "conversation_id": self.task_id,
            "seq": self.seq,
            "run_id": self.run_id,
            "step_id": step_id,
            "ts": _now(),
            "source": "runner",
            "payload": payload,
        }
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        if len(line.encode("utf-8")) > _MAX_EVENT_BYTES:
            raise RunnerError("journal record exceeds the 1 MB limit", EXIT_INTERNAL)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        self.events += 1


class Plan:
    """The step checklist carried by every `plan_update`."""

    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.revision = 0
        self.status = {step: "pending" for step in STEPS}

    def update(self, step: str, status: str) -> None:
        self.status[step] = status
        self.revision += 1
        self.journal.append(
            "plan_update",
            {
                "revision": self.revision,
                "steps": [
                    {"step_id": name, "label_code": name, "status": self.status[name]}
                    for name in STEPS
                ],
            },
            step_id=step,
        )


def _run_cli(
    module: str, args: list[str], *, repo_root: Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    """Run one pipeline CLI as a subprocess (no imports, no shared state)."""
    command = [sys.executable, "-m", module, *args]
    return subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _module_available(module: str, *, repo_root: Path) -> bool:
    """True when the CLI module has a `__main__` entry point."""
    parts = module.split(".")
    return (repo_root.joinpath(*parts) / "__main__.py").is_file()


def _skipped_stage(journal: Journal, plan: Plan, step: str, reason: str) -> None:
    journal.append(
        "error",
        {"code": reason, "correlation_id": step, "retry": {"kind": "none"}},
        step_id=step,
    )
    plan.update(step, "skipped")


def _failed_stage(journal: Journal, plan: Plan, step: str, reason: str) -> None:
    journal.append(
        "error",
        {"code": reason, "correlation_id": step, "retry": {"kind": "manual"}},
        step_id=step,
    )
    plan.update(step, "failed")


def _run_cli_stage(
    journal: Journal, step: str, command_id: str, label_code: str, module: str,
    args: list[str], *, repo_root: Path, timeout: int,
) -> subprocess.CompletedProcess[str] | None:
    """Run one CLI with H11 started/output/finished command events; None on timeout."""
    base = {"command_id": command_id, "label_code": label_code, "display_cwd": "artifacts"}

    def event(phase: str, **fields: Any) -> None:
        journal.append("command", {**base, "phase": phase, **fields}, step_id=step)

    event("started")
    try:
        result = _run_cli(module, args, repo_root=repo_root, timeout=timeout)
    except subprocess.TimeoutExpired:
        event("output", text=f"timeout after {timeout}s\n", truncated=False)
        event("finished", exit_code=None)
        return None
    text = result.stderr or result.stdout or ""
    event("output", text=text[-2000:], truncated=len(text) > 2000)
    event("finished", exit_code=result.returncode)
    return result


def _artifact_row(display_path: str, digest: str, note: str) -> dict[str, Any]:
    """One H11 `file_change.files` row: display path, counts and a hashed note."""
    diff = {"text": f"{note} sha256={digest}\n", "truncated": False}
    return {"display_path": display_path, "added": 1, "removed": 0, "diff": diff}


def _valid_repair_output(summary: dict[str, Any], artifacts: Path) -> bool:
    """Check that the apply CLI summary and the artifacts it claims to write agree."""
    claimed = {"candidate_sha256": "candidate.elf",
               "manifest_file_sha256": "edit-manifest.json",
               "candidate_record_sha256": "candidate-v1.json"}
    return (
        summary.get("candidate_written") is True
        and summary.get("fixture_unchanged") is True
        and summary.get("executed_on_host") is False
        and _is_sha256(summary.get("manifest_sha256"))
        and all(_is_sha256(summary.get(field)) and (artifacts / name).is_file()
                and _sha256_file(artifacts / name) == summary[field]
                for field, name in claimed.items())
    )


def _stage_repair(
    journal: Journal, plan: Plan, task: dict[str, Any], binary: Path,
    plan_path: Path, artifacts: Path, repo_root: Path,
) -> StageOutcome:
    plan.update("repair", "in_progress")
    if not plan_path.is_file():
        _failed_stage(journal, plan, "repair", "repair_plan_missing")
        return StageOutcome("repair_plan_missing")
    args = ["--elf", str(binary), "--plan", str(plan_path),
            "--out-dir", str(artifacts), "--fixture-id", str(task["fixture_id"])]
    result = _run_cli_stage(
        journal, "repair", "repair-1", "repair", "pipeline.repair.apply_fixplan", args,
        repo_root=repo_root, timeout=_REPAIR_TIMEOUT_S)
    if result is None:
        _failed_stage(journal, plan, "repair", "repair_timeout")
        return StageOutcome("repair_timeout")
    if result.returncode != 0:
        _failed_stage(journal, plan, "repair", "repair_failed")
        return StageOutcome("repair_failed")
    summary = _read_json_text(result.stdout)
    if summary is None or not _valid_repair_output(summary, artifacts):
        _failed_stage(journal, plan, "repair", "repair_output_invalid")
        return StageOutcome("repair_output_invalid")
    files = [
        _artifact_row("candidate.elf", summary["candidate_sha256"],
                      "applied approved FixPlanV1;"),
        _artifact_row("edit-manifest.json", summary["manifest_file_sha256"],
                      f"EditManifestV1 manifest_sha256={summary['manifest_sha256']};"),
        _artifact_row("candidate-v1.json", summary["candidate_record_sha256"],
                      "CandidateV1 applied-candidate record;"),
    ]
    journal.append("file_change", {"change_id": "repair-1", "stage": "applied",
                                   "files": files}, step_id="repair")
    plan.update("repair", "completed")
    return StageOutcome(files=len(files))


def _stage_verify(
    journal: Journal, plan: Plan, task: dict[str, Any], binary: Path,
    artifacts: Path, repo_root: Path,
) -> StageOutcome:
    plan.update("verify", "in_progress")
    observations = artifacts / _OBSERVATIONS_FILE
    if not observations.is_file():
        _skipped_stage(journal, plan, "verify", "verify_observations_missing")
        return StageOutcome("verify_observations_missing")
    fixture = repo_root / "fixtures" / str(task["fixture_id"])
    verdict_path = artifacts / _VERDICT_FILE
    args = ["--contract", str(fixture / "contract.json"),
            "--cases", str(fixture / "cases" / "cases.json"),
            "--observations", str(observations),
            "--manifest", str(artifacts / "edit-manifest.json"),
            "--original-elf", str(binary),
            "--candidate-elf", str(artifacts / "candidate.elf"),
            "--out", str(verdict_path)]
    result = _run_cli_stage(
        journal, "verify", "verify-1", "verification", "pipeline.verify.verdict", args,
        repo_root=repo_root, timeout=_VERIFY_TIMEOUT_S)
    if result is None:
        _failed_stage(journal, plan, "verify", "verify_timeout")
        return StageOutcome("verify_timeout")
    if result.returncode not in (0, 1) or not verdict_path.is_file():
        _failed_stage(journal, plan, "verify", "verify_failed")
        return StageOutcome("verify_failed")
    try:
        verdict = _read_json_text(verdict_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        verdict = None
    label = verdict.get("verdict") if verdict is not None else None
    if label not in _VERDICT_VOCABULARY:
        _failed_stage(journal, plan, "verify", "verify_verdict_invalid")
        return StageOutcome("verify_verdict_invalid")
    if (result.returncode == 0) != (label == _VERIFIED):
        _failed_stage(journal, plan, "verify", "verify_inconsistent")
        return StageOutcome("verify_inconsistent")
    summary = _read_json_text(result.stdout) or {}
    evaluation_id = summary.get("verdict_sha256") or _sha256_file(verdict_path)
    generated_at = verdict.get("produced_at")
    journal.append("verification", {
        "kind": "evaluation", "evaluation_id": evaluation_id, "verdict": label,
        "generated_at": generated_at if isinstance(generated_at, str) else _now(),
    }, step_id="verify")
    files = [_artifact_row(_VERDICT_FILE, _sha256_file(verdict_path),
                           f"VerdictV1 verdict={label};")]
    journal.append("file_change", {"change_id": "verify-1", "stage": "applied",
                                   "files": files}, step_id="verify")
    plan.update("verify", "completed")
    return StageOutcome(files=1, evaluation_id=evaluation_id)


def run_task(task_id: str, *, var_root: Path, repo_root: Path) -> dict[str, Any]:
    """Execute one approved task and return the stdout summary."""
    started = time.monotonic()
    task = load_task(var_root, task_id)
    check_approval(task)
    binary = resolve_binary(repo_root, task)
    plan_path = resolve_plan(repo_root, task)
    contract_path = repo_root / "fixtures" / str(task["fixture_id"]) / "contract.json"
    if contract_path.is_file() and _sha256_file(contract_path) != task.get("contract_sha256"):
        raise RunnerError("contract does not match the approved task", EXIT_NOT_APPROVED)

    execution = task.get("execution") or {}
    run_id = execution.get("run_id") or f"run_{task_id[-12:]}"
    journal = Journal(var_root, task_id, run_id)
    plan = Plan(journal)
    artifacts = var_root / "artifacts" / task_id
    files_changed = 0
    evaluation_id: str | None = None
    reason_code: str | None = None

    journal.append("run_state", {"status": "running", "message_id": None})
    corpus = task.get("corpus") or {}
    journal.append(
        "corpus_update",
        {
            "fixture_id": task["fixture_id"],
            "counts": corpus.get("counts") or {"valid": 0, "invalid": 0, "poc": 0},
            "total": corpus.get("total", 0),
            "cases_sha256": corpus.get("cases_sha256"),
        },
    )

    try:
        plan.update("collect", "in_progress")
        plan.update("collect", "completed")
        plan.update("freeze", "completed")

        analyze_code: str | None = None
        plan.update("analyze", "in_progress")
        if not _module_available("pipeline.analyze", repo_root=repo_root):
            _skipped_stage(journal, plan, "analyze", "analyze_not_wired")
            analyze_code = "analyze_not_wired"
        else:
            journal.append(
                "command",
                {
                    "command_id": "analyze-1",
                    "phase": "started",
                    "label_code": "analysis",
                    "display_cwd": "evidence",
                },
                step_id="analyze",
            )
            result = _run_cli(
                "pipeline.analyze",
                ["--elf", str(binary), "--out-dir", str(artifacts)],
                repo_root=repo_root,
                timeout=_ANALYZE_TIMEOUT_S,
            )
            journal.append(
                "command",
                {
                    "command_id": "analyze-1",
                    "phase": "finished",
                    "label_code": "analysis",
                    "display_cwd": "evidence",
                    "exit_code": result.returncode,
                    "text": (result.stderr or result.stdout or "")[-2000:],
                    "truncated": len(result.stderr or result.stdout or "") > 2000,
                },
                step_id="analyze",
            )
            if result.returncode != 0:
                _failed_stage(journal, plan, "analyze", "analyze_failed")
                analyze_code = "analyze_failed"
            else:
                produced = [artifacts / "disassembly.json", artifacts / "finding.json"]
                files = [
                    _artifact_row(item.name, _sha256_file(item), "generated by pipeline.analyze;")
                    for item in produced
                    if item.is_file()
                ]
                files_changed += len(files)
                journal.append(
                    "file_change",
                    {"change_id": "analyze-1", "stage": "proposed", "files": files},
                    step_id="analyze",
                )
                plan.update("analyze", "completed")

        if analyze_code is not None:
            reason_code = analyze_code
            for step in ("repair", "verify"):
                _skipped_stage(journal, plan, step, analyze_code)
        else:
            repair = _stage_repair(journal, plan, task, binary, plan_path, artifacts, repo_root)
            files_changed += repair.files
            if repair.reason is not None:
                reason_code = repair.reason
                _skipped_stage(journal, plan, "verify", repair.reason)
            else:
                verify = _stage_verify(journal, plan, task, binary, artifacts, repo_root)
                files_changed += verify.files
                evaluation_id = verify.evaluation_id
                reason_code = verify.reason

        for step in ("audit", "decision", "export"):
            _skipped_stage(journal, plan, step, "stage_not_wired")
        if reason_code is None:
            reason_code = "stages_not_wired"
    except subprocess.TimeoutExpired:
        journal.append(
            "error",
            {"code": "analyze_timeout", "correlation_id": "analyze", "retry": {"kind": "manual"}},
            step_id="analyze",
        )
        reason_code = "analyze_timeout"
    except OSError as error:
        journal.append(
            "error",
            {"code": "runner_io_error", "correlation_id": "runner", "retry": {"kind": "manual"}},
        )
        reason_code = f"runner_io_error: {error.__class__.__name__}"
    finally:
        journal.append(
            "run_end",
            {
                "execution": "failed",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "steps_taken": sum(1 for value in plan.status.values() if value == "completed"),
                "files_changed": files_changed,
                "ai": {"calls": None, "tokens": None, "cost_usd": None},
                "evaluation_id": evaluation_id,
            },
        )

    return {"task_id": task_id, "run_id": run_id, "execution": "failed",
            "reason_code": reason_code, "events": journal.events}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True, help="task id, e.g. tsk_ab12cd34ef56ab78cd90ef12")
    parser.add_argument("--var-root", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)

    repo_root = (args.repo_root or Path(__file__).resolve().parents[1]).resolve()
    var_root = (args.var_root or repo_root / "var").resolve()
    try:
        summary = run_task(args.task, var_root=var_root, repo_root=repo_root)
    except RunnerError as error:
        print(
            json.dumps({"task_id": args.task, "error": str(error), "exit_code": error.code}),
            file=sys.stderr,
        )
        return error.code
    print(json.dumps(summary, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
