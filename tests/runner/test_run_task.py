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
    assert summary["reason_code"] is None
    assert summary["execution"] == "completed"

    records = _journal(tmp_path)
    evaluations = [record["payload"] for record in records if record["type"] == "verification"]
    assert len(evaluations) == 1
    assert evaluations[0]["verdict"] == "verified_against_stated_criteria"
    assert records[-1]["payload"]["execution"] == "completed"
    assert records[-1]["payload"]["evaluation_id"] == evaluations[0]["evaluation_id"]

    artifacts = tmp_path / "artifacts" / TASK_ID
    assert _sha(artifacts / "candidate.elf") == _sha_bytes(candidate)
    verdict = json.loads((artifacts / "verdict.json").read_text(encoding="utf-8"))
    schema = json.loads((REPO / "schemas" / "VerdictV1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(verdict, schema)
    assert verdict["verdict"] == "verified_against_stated_criteria"

    steps = _steps(records)
    assert steps["decision"] == steps["repair"] == steps["verify"] == "completed"
    assert steps["audit"] == "skipped"
    assert _errors(records)["audit"] == "satisfied_by_signed_g2"
    assert steps["export"] == "completed"
    bundle = json.loads((artifacts / "export" / "bundle-manifest.json").read_text(encoding="utf-8"))
    assert bundle["verdict"] == "verified_against_stated_criteria"
    assert bundle["verdict_sha256"] == _sha(artifacts / "verdict.json")
    names = {item["name"] for item in bundle["artifacts"]}
    assert {"candidate.elf", "edit-manifest.json", "candidate-v1.json", "verdict.json"} <= names
    # 2 analysis + 3 repair + 1 verdict + 1 export
    assert records[-1]["payload"]["files_changed"] == 7


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
    assert errors["audit"] == errors["export"] == "decision_missing"
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()
    assert "verified_against_stated_criteria" not in json.dumps(records)


def test_runner_blocks_repair_when_decision_is_not_proceed(tmp_path: Path, capsys) -> None:
    assert _run(tmp_path, decision="iterate") == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reason_code"] == "decision_not_proceed"

    records = _journal(tmp_path)
    steps = _steps(records)
    assert steps["decision"] == "completed"
    assert steps["repair"] == steps["verify"] == steps["export"] == "skipped"
    assert _errors(records)["repair"] == "decision_not_proceed"
    assert _errors(records)["audit"] == "satisfied_by_signed_g2"
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

# ---------------------------------------------------------------------------
# G4.1 live mode (audit_mode=live, live_guest)
# ---------------------------------------------------------------------------
CANONICAL_PLAN = "6f5f3535f3103acd04665aa4e19a2e8b6075ab7f8bc9657f5f53f01a2693ae1a"


def _live_task() -> dict:
    task = _task()
    task["audit_mode"] = "live"
    task["plan"] = "docs/audit/fix-plan-v1.json"
    task["live_audit"] = {
        "status": "completed",
        "model": "deepseek-v4-pro",
        "runs": [
            {"run_index": 1, "schema_valid": True, "plan_sha256": "a" * 64,
             "plan_path": "var/audit/x/run-1.json", "usage": {"total_tokens": 10}},
            {"run_index": 2, "schema_valid": True, "plan_sha256": "b" * 64,
             "plan_path": "var/audit/x/run-2.json", "usage": {"total_tokens": 11}},
            {"run_index": 3, "schema_valid": False, "plan_sha256": "c" * 64,
             "plan_path": "var/audit/x/run-3.json", "usage": {"total_tokens": 12}},
        ],
    }
    task["selected_plan"] = {
        "source": "live",
        "run_index": 2,
        "path": "docs/audit/fix-plan-v1.json",
        "file_sha256": "d" * 64,
        "canonical_sha256": CANONICAL_PLAN,
    }
    task["approval"]["plan_sha256"] = CANONICAL_PLAN
    return task


def _fake_guest(tmp_path: Path, observations: dict, *, fail: bool = False) -> Path:
    script = tmp_path / "fake_guest.py"
    if fail:
        script.write_text(
            "import sys\n"
            "sys.stderr.write('guest_unavailable: wsl.exe not found\\n')\n"
            "sys.exit(3)\n",
            encoding="utf-8",
        )
        return script
    sidecar = tmp_path / "fake_observations.json"
    sidecar.write_text(json.dumps(observations), encoding="utf-8")
    script.write_text(
        "import argparse, json, pathlib\n"
        "parser = argparse.ArgumentParser()\n"
        "for name in ('--original', '--candidate', '--cases', '--out-dir', '--timeout'):\n"
        "    parser.add_argument(name)\n"
        "args = parser.parse_args()\n"
        "out = pathlib.Path(args.out_dir)\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        f"data = pathlib.Path({str(sidecar)!r}).read_text(encoding='utf-8')\n"
        "for name in ('observations-original.json', 'observations-candidate.json'):\n"
        "    (out / name).write_text(data, encoding='utf-8')\n"
        "(out / 'guest-environment.json').write_text("
        "json.dumps({'distro': 'Ubuntu', 'kernel': 'fake', 'libc': 'glibc fake'}),"
        " encoding='utf-8')\n",
        encoding="utf-8",
    )
    return script


def test_runner_live_audit_is_bound_from_the_task_snapshot(tmp_path: Path, capsys) -> None:
    candidate = _seed_candidate(tmp_path)
    capsys.readouterr()

    _write_task(tmp_path, _live_task())
    _write_decision(tmp_path)
    observations = tmp_path / "artifacts" / TASK_ID / "observations-candidate.json"
    observations.parent.mkdir(parents=True, exist_ok=True)
    observations.write_text(json.dumps(_observations(candidate)), encoding="utf-8")
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution"] == "completed"

    records = _journal(tmp_path)
    steps = _steps(records)
    assert steps["audit"] == "completed"
    assert steps["decision"] == steps["repair"] == steps["verify"] == "completed"
    audit_rows = [record for record in records if record["type"] == "audit_runs"]
    assert len(audit_rows) == 1
    assert len(audit_rows[0]["payload"]["runs"]) == 3
    assert audit_rows[0]["payload"]["runs"][0]["run_index"] == 1
    errors = _errors(records)
    assert "satisfied_by_signed_g2" not in errors.values()


def test_runner_live_audit_missing_is_honest(tmp_path: Path, capsys) -> None:
    task = _live_task()
    task["live_audit"]["status"] = "failed"
    _write_task(tmp_path, task)
    _write_decision(tmp_path)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution"] == "failed"
    assert summary["reason_code"] == "live_audit_failed"
    records = _journal(tmp_path)
    assert _steps(records)["audit"] == "failed"
    assert _errors(records)["audit"] == "live_audit_failed"
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()


def test_runner_live_plan_needs_the_approval_binding(tmp_path: Path, capsys) -> None:
    task = _live_task()
    task["approval"]["plan_sha256"] = "0" * 64
    _write_task(tmp_path, task)
    _write_decision(tmp_path)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["reason_code"] == "plan_not_approved"
    records = _journal(tmp_path)
    assert _steps(records)["decision"] == "failed"
    assert _errors(records)["decision"] == "plan_not_approved"
    assert not (tmp_path / "artifacts" / TASK_ID / "candidate.elf").exists()


def test_runner_live_guest_uses_fresh_observations(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    candidate = _seed_candidate(tmp_path)
    capsys.readouterr()
    task = _live_task()
    task["live_guest"] = True
    _write_task(tmp_path, task)
    _write_decision(tmp_path)
    script = _fake_guest(tmp_path, _observations(candidate))
    monkeypatch.setattr(run_task, "_GUEST_DRIVER", script)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution"] == "completed"

    records = _journal(tmp_path)
    guest = [record for record in records
             if record["type"] == "verification" and record["payload"].get("kind") == "guest"]
    assert len(guest) == 1
    assert guest[0]["payload"]["status"] == "passed"
    assert guest[0]["payload"]["environment"]["kernel"] == "fake"
    live_dir = tmp_path / "artifacts" / TASK_ID / "live-guest"
    assert (live_dir / "observations-candidate.json").is_file()
    assert (live_dir / "guest-environment.json").is_file()
    verdict = json.loads((tmp_path / "artifacts" / TASK_ID / "verdict.json").read_text())
    assert verdict["verdict"] == "verified_against_stated_criteria"


def test_runner_live_guest_failure_is_honest(tmp_path: Path, monkeypatch, capsys) -> None:
    task = _live_task()
    task["live_guest"] = True
    _write_task(tmp_path, task)
    _write_decision(tmp_path)
    script = _fake_guest(tmp_path, {}, fail=True)
    monkeypatch.setattr(run_task, "_GUEST_DRIVER", script)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["execution"] == "failed"
    assert summary["reason_code"] == "guest_unavailable"
    records = _journal(tmp_path)
    assert _steps(records)["verify"] == "failed"
    assert _errors(records)["verify"] == "guest_unavailable"
    assert not (tmp_path / "artifacts" / TASK_ID / "verdict.json").exists()

