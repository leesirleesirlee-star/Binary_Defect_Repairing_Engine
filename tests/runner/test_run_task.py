"""Tests for the local task runner (scripts/run_task.py)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema

from scripts.run_task import main

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "fixtures" / "stack-overflow-01"
TASK_ID = "tsk_ab12cd34ef56ab78cd90ef12"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _journal(var_root: Path) -> list[dict]:
    path = var_root / "events" / f"{TASK_ID}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_runner_emits_analyze_events_and_fails_honestly(tmp_path: Path) -> None:
    _write_task(tmp_path, _task())
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 0

    records = _journal(tmp_path)
    assert [record["seq"] for record in records] == list(range(1, len(records) + 1))
    assert all(record["version"] == 1 and record["source"] == "runner" for record in records)
    types = [record["type"] for record in records]
    assert "run_state" in types
    assert "corpus_update" in types
    assert "plan_update" in types
    assert "file_change" in types
    assert "run_end" in types

    end = records[-1]
    assert end["type"] == "run_end"
    assert end["payload"]["execution"] == "failed"
    assert end["payload"]["ai"] == {"calls": None, "tokens": None, "cost_usd": None}
    serialized = json.dumps(records)
    assert "verified_against_stated_criteria" not in serialized

    view = tmp_path / "artifacts" / TASK_ID / "disassembly.json"
    assert view.is_file()
    schema = json.loads(
        (REPO / "schemas" / "DisassemblyViewV1.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(json.loads(view.read_text(encoding="utf-8")), schema)


def test_runner_refuses_unapproved_task(tmp_path: Path) -> None:
    task = _task()
    task["approval"] = {"approved": False}
    _write_task(tmp_path, task)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 3
    assert not (tmp_path / "events" / f"{TASK_ID}.jsonl").exists()


def test_runner_refuses_stale_approval(tmp_path: Path) -> None:
    task = _task()
    task["approval"]["binding_digest"] = "0" * 64
    _write_task(tmp_path, task)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 3
    assert not (tmp_path / "events" / f"{TASK_ID}.jsonl").exists()


def test_runner_refuses_unknown_task(tmp_path: Path) -> None:
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 2


def test_runner_refuses_binary_digest_mismatch(tmp_path: Path) -> None:
    task = _task()
    task["binary"]["sha256"] = "0" * 64
    _write_task(tmp_path, task)
    assert main(["--task", TASK_ID, "--var-root", str(tmp_path), "--repo-root", str(REPO)]) == 2
    assert not (tmp_path / "events" / f"{TASK_ID}.jsonl").exists()
