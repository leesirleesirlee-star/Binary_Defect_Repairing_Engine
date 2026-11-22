"""Tests for the local task runner (scripts/run_task.py).

Nothing here executes an ELF: the stages run the deterministic CLIs and the
candidate observations are synthetic `ObservationV1` documents. Cancellation is
exercised with a slow non-ELF fake child process only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
import time
from pathlib import Path

import jsonschema

from scripts import run_task
from scripts.run_task import main

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "fixtures" / "stack-overflow-01"
TASK_ID = "tsk_ab12cd34ef56ab78cd90ef12"


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _task() -> dict:
    manifest = json.loads((FIXTURE / "fixture-manifest.json").read_text(encoding="utf-8"))
    cases = json.loads((FIXTURE / "cases" / "cases.json").read_text(encoding="utf-8"))
    counts = {"valid": 0, "invalid": 0, "poc": 0}
    for case in cases["cases"]:
        counts[case["kind"]] += 1
    binding = "f" * 64
    return {
        "id": TASK_ID,
        "fixture_id": "stack-overflow-01",
        "phase": "approved",
        "binary": {
            "path": manifest["binary"]["path"],
            "sha256": manifest["binary"]["sha256"],
            "size": manifest["binary"]["size"],
        },
        "corpus": {
            "counts": counts,
            "total": len(cases["cases"]),
            "cases_sha256": _sha(FIXTURE / "cases" / "cases.json"),
        },
        "contract_sha256": _sha(FIXTURE / "contract.json"),
        "review_binding_digest": binding,
        "approval": {"approved": True, "binding_digest": binding},
        "execution": {"run_id": "run_test", "status": "running"},
    }


def _write_task(var_root: Path, task: dict) -> None:
    path = var_root / "tasks" / f"{task['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task), encoding="utf-8")


def _write_decision(var_root: Path, decision: str = "proceed") -> None:
    """Write the GUI `POST /decision` journal entry (`user_response`)."""
    path = var_root / "events" / f"{TASK_ID}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "version": 1,
        "type": "user_response",
        "conversation_id": TASK_ID,
        "seq": 1,
        "run_id": None,
        "step_id": "decision",
        "ts": "2026-11-22T00:00:00Z",
        "source": "gui",
        "payload": {"request_id": "decision-1", "kind": "audit_decision",
                    "decision": decision},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _run(var_root: Path, task: dict | None = None, *, decision: str | None = "proceed") -> int:
    _write_task(var_root, task or _task())
    if decision is not None:
        _write_decision(var_root, decision)
    return main(["--task", TASK_ID, "--var-root", str(var_root), "--repo-root", str(REPO)])


def _journal(var_root: Path) -> list[dict]:
    path = var_root / "events" / f"{TASK_ID}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _steps(records: list[dict]) -> dict[str, str]:
    updates = [record for record in records if record["type"] == "plan_update"]
    return {step["step_id"]: step["status"] for step in updates[-1]["payload"]["steps"]}


def _errors(records: list[dict]) -> dict[str, str]:
    return {
        record["payload"]["correlation_id"]: record["payload"]["code"]
        for record in records
        if record["type"] == "error"
    }


def _seed_candidate(tmp_path: Path) -> bytes:
    """Run the approved task once and return the deterministic candidate bytes."""
    seed = tmp_path / "seed"
    assert _run(seed) == 0
    return (seed / "artifacts" / TASK_ID / "candidate.elf").read_bytes()


def _observations(candidate: bytes) -> dict:
    """Synthetic candidate observations from the frozen corpus (data, not execution)."""
    cases = json.loads((FIXTURE / "cases" / "cases.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    for case in cases:
        expected = case["expected_candidate"]
        rows.append(
            {
                "id": case["id"],
                "argv_sha256": _sha_bytes(
                    json.dumps(case["argv"], separators=(",", ":")).encode()
                ),
                "exit_code": expected.get("exit_code"),
                "signal": expected.get("signal"),
                "stdout_b64": base64.b64encode(expected.get("stdout", "").encode()).decode(),
                "stderr_b64": base64.b64encode(expected.get("stderr", "").encode()).decode(),
                "duration_ms": 3,
                "timed_out": False,
            }
        )
    return {
        "schema_version": 1,
        "binary": {"path": "candidate.elf", "sha256": _sha_bytes(candidate)},
        "environment": {"uname": "Linux runner-test", "kernel": "test", "libc": "glibc test"},
        "started_at": "2026-11-22T00:00:00Z",
        "cases": rows,
    }


def test_runner_runs_repair_and_skips_verify_without_observations(
    tmp_path: Path, capsys
) -> None:
    task = _task()
    task["plan"] = "docs/audit/fix-plan-v1.json"  # explicit override of the default
    assert _run(tmp_path, task) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reason_code"] == "verify_observations_missing"

    records = _journal(tmp_path)
    assert [record["seq"] for record in records] == list(range(1, len(records) + 1))
    assert records[-1]["type"] == "run_end"
    assert records[-1]["payload"]["execution"] == "failed"
    assert records[-1]["payload"]["files_changed"] == 5  # 2 analysis + 3 repair
    assert "verified_against_stated_criteria" not in json.dumps(records)
    steps = _steps(records)
    assert (steps["decision"], steps["repair"], steps["verify"]) == (
        "completed",
        "completed",
        "skipped",
    )
    assert _errors(records)["verify"] == "verify_observations_missing"

    artifacts = tmp_path / "artifacts" / TASK_ID
    for name in ("candidate.elf", "edit-manifest.json", "candidate-v1.json", "disassembly.json"):
        assert (artifacts / name).is_file()
    schema = json.loads((REPO / "schemas" / "CandidateV1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(json.loads((artifacts / "candidate-v1.json").read_text()), schema)
    applied = [item["display_path"] for record in records if record["type"] == "file_change"
               and record["payload"]["stage"] == "applied" for item in record["payload"]["files"]]
    assert applied == ["candidate.elf", "edit-manifest.json", "candidate-v1.json"]
    assert _sha(artifacts / "candidate.elf") in json.dumps(records)


def test_runner_records_verdict_from_synthetic_observations(
    tmp_path: Path, capsys
) -> None:
    candidate = _seed_candidate(tmp_path)
    capsys.readouterr()

    _write_task(tmp_path, _task())
    _write_decision(tmp_path)
    observations = tmp_path / "artifacts" / TASK_ID / "observations-candidate.json"
    observations.parent.mkdir(parents=True)
    observations.write_text(json.dumps(_observations(candidate)), encoding="utf-8")
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reason_code"] == "stages_not_wired"

    records = _journal(tmp_path)
    evaluations = [record["payload"] for record in records if record["type"] == "verification"]
    assert len(evaluations) == 1
    assert evaluations[0]["verdict"] == "verified_against_stated_criteria"
    assert records[-1]["payload"]["execution"] == "failed"
    assert records[-1]["payload"]["evaluation_id"] == evaluations[0]["evaluation_id"]

    artifacts = tmp_path / "artifacts" / TASK_ID
    assert _sha(artifacts / "candidate.elf") == _sha_bytes(candidate)
    verdict = json.loads((artifacts / "verdict.json").read_text(encoding="utf-8"))
    schema = json.loads((REPO / "schemas" / "VerdictV1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(verdict, schema)
    assert verdict["verdict"] == "verified_against_stated_criteria"


def test_runner_blocks_repair_without_persisted_decision(tmp_path: Path, capsys) -> None:
    assert _run(tmp_path, decision=None) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reason_code"] == "decision_missing"

    records = _journal(tmp_path)
    steps = _steps(records)
    assert (steps["decision"], steps["repair"], steps["verify"]) == (
        "skipped",
        "skipped",
        "skipped",
    )
    errors = _errors(records)
    assert errors["decision"] == errors["repair"] == errors["verify"] == "decision_missing"
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()
    assert "verified_against_stated_criteria" not in json.dumps(records)


def test_runner_blocks_repair_when_decision_is_not_proceed(tmp_path: Path, capsys) -> None:
    assert _run(tmp_path, decision="iterate") == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reason_code"] == "decision_not_proceed"

    records = _journal(tmp_path)
    assert _steps(records)["decision"] == "completed"
    assert _steps(records)["repair"] == "skipped"
    assert _errors(records)["repair"] == "decision_not_proceed"
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()


def test_runner_accepts_proceed_decision_from_task_state(tmp_path: Path) -> None:
    task = _task()
    task["decision"] = "proceed"
    assert _run(tmp_path, task, decision=None) == 0
    assert (tmp_path / "artifacts" / TASK_ID / "candidate.elf").is_file()


def test_runner_records_honest_cancel_terminal(tmp_path: Path, capsys) -> None:
    task = _task()
    task["execution"] = {"run_id": "run_test", "status": "cancelled", "terminal": True,
                         "reason_code": "user_cancelled"}
    assert _run(tmp_path, task) == 5
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution"] == "cancelled"
    assert summary["reason_code"] == "user_cancelled"

    records = _journal(tmp_path)
    assert records[-1]["type"] == "run_end"
    assert records[-1]["payload"]["execution"] == "cancelled"
    assert _errors(records)["analyze"] == "user_cancelled"
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()


def test_runner_terminates_running_child_on_cancel(tmp_path: Path, monkeypatch) -> None:
    real_process = run_task._run_cli_process

    def slow_cli(module, args, *, repo_root, timeout, should_cancel=None):
        return real_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            repo_root=repo_root,
            timeout=timeout,
            should_cancel=should_cancel,
        )

    monkeypatch.setattr(run_task, "_run_cli", slow_cli)
    _write_task(tmp_path, _task())
    _write_decision(tmp_path)

    def cancel() -> None:
        path = tmp_path / "tasks" / f"{TASK_ID}.json"
        task = json.loads(path.read_text(encoding="utf-8"))
        task["execution"] = {"run_id": "run_test", "status": "cancelled"}
        path.write_text(json.dumps(task), encoding="utf-8")

    timer = threading.Timer(0.3, cancel)
    started = time.monotonic()
    timer.start()
    try:
        code = main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)])
    finally:
        timer.cancel()
    elapsed = time.monotonic() - started

    assert code == 5  # the 30 s fake child was terminated, not awaited
    assert elapsed < 20
    records = _journal(tmp_path)
    assert records[-1]["payload"]["execution"] == "cancelled"
    assert _errors(records)["analyze"] == "user_cancelled"


def test_runner_refuses_unapproved_task(tmp_path: Path) -> None:
    task = _task()
    task["approval"] = {"approved": False}
    assert _run(tmp_path, task, decision=None) == 3
    assert not (tmp_path / "events" / f"{TASK_ID}.jsonl").exists()
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()


def test_runner_refuses_stale_approval(tmp_path: Path) -> None:
    task = _task()
    task["approval"]["binding_digest"] = "0" * 64
    assert _run(tmp_path, task, decision=None) == 3
    assert not (tmp_path / "events" / f"{TASK_ID}.jsonl").exists()


def test_runner_refuses_unknown_task(tmp_path: Path) -> None:
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 2


def test_runner_refuses_binary_digest_mismatch(tmp_path: Path) -> None:
    task = _task()
    task["binary"]["sha256"] = "0" * 64
    assert _run(tmp_path, task, decision=None) == 2
    assert not (tmp_path / "events" / f"{TASK_ID}.jsonl").exists()
