"""G4.1 live mode backend tests with a fake audit child (no key, no WSL)."""

from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import assistant_key, live_audit, tasks
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01" / "vuln.elf"
PLAN = ROOT / "docs" / "audit" / "fix-plan-v1.json"
CANONICAL = "6f5f3535f3103acd04665aa4e19a2e8b6075ab7f8bc9657f5f53f01a2693ae1a"


class FakeProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        session = test_client.get("/api/session")
        assert session.status_code == 200
        test_client.headers.update({"x-csrf-token": session.json()["csrf_token"]})
        yield test_client


class BlockingProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.release = threading.Event()

    def wait(self, timeout: float | None = None) -> int:
        self.release.wait(timeout)
        return 143

    def terminate(self) -> None:
        self.terminated = True
        self.release.set()

    def kill(self) -> None:
        self.killed = True
        self.release.set()


def _blocking_spawn(seen: list[BlockingProcess]):
    def spawn(command: list[str], env: dict[str, str]) -> BlockingProcess:
        process = BlockingProcess()
        seen.append(process)
        return process
    return spawn


def _prepare_task(task_id: str, *, running: bool) -> None:
    task = tasks.get(task_id)
    task["audit_mode"] = "live"
    task["live_audit"] = {
        "status": "running" if running else "completed", "model": "deepseek-v4-pro",
        "started_at": "2026-11-24T00:00:00Z", "finished_at": None, "error": None,
        "runs": [],
    }
    task["selected_plan"] = {"source": "live", "run_index": 1,
                             "path": "var/audit/x.json", "file_sha256": "a" * 64,
                             "canonical_sha256": "b" * 64}
    task["approval"] = {"approved": True}
    task["decision"] = {"decision": "proceed"}
    tasks.update(task)


def _upload(client: TestClient) -> str:
    payload = base64.b64encode(FIXTURE.read_bytes()).decode("ascii")
    cases = [
        {"name": "valid.json", "content_base64": base64.b64encode(b'{"valid":["","A"]}').decode()},
        {"name": "poc.json", "content_base64": base64.b64encode(
            b'{"invalid":["' + b"A" * 64 + b'"]}').decode()},
    ]
    response = client.post("/api/tasks/upload", json={
        "binary_name": "vuln.elf", "binary_base64": payload, "case_files": cases,
    })
    assert response.status_code == 201, response.text
    return response.json()["task"]["id"]


def _fake_spawn(returncode: int = 0):
    def spawn(command: list[str], env: dict[str, str]) -> FakeProcess:
        assert command[1:3] == ["-m", "pipeline.audit"]
        assert "--runs" in command and command[command.index("--runs") + 1] == "1"
        assert "--model" in command and "deepseek-v4-pro" in command
        assert env["DEEPSEEK_API_KEY"] == "sk-test-live-1234567890"
        summary_index = command.index("--summary-out") + 1
        summary_path = ROOT / command[summary_index]
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps({
            "model": "deepseek-v4-pro",
            "prompt_sha256": "a" * 64,
            "contract_sha256": "b" * 64,
            "runs": [{
                "run_index": 1,
                "schema_valid": True,
                "plan_sha256": "1" * 64,
                "plan_path": None,
                "plan": json.loads(PLAN.read_text(encoding="utf-8")),
                "usage": {"total_tokens": 101},
            }],
        }), encoding="utf-8")
        return FakeProcess(returncode)
    return spawn


def _start(client: TestClient, task_id: str, monkeypatch: pytest.MonkeyPatch,
           spawn=None) -> dict[str, Any]:
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-live-1234567890")
    monkeypatch.setattr(live_audit, "_spawn", spawn or _fake_spawn())
    response = client.post(f"/api/tasks/{task_id}/audit/live", json={})
    assert response.status_code == 202, response.text
    return live_audit.wait_for_terminal(task_id)


def test_fake_child_records_three_runs_and_no_key(client: TestClient,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload(client)
    live = _start(client, task_id, monkeypatch)
    assert live["status"] == "completed"
    assert len(live["runs"]) == 3
    assert live["prompt_sha256"] == "a" * 64
    body = client.get(f"/api/tasks/{task_id}/audit").json()
    assert body["audit_mode"] == "live"
    assert body["live_audit"]["prompt_sha256"] == "a" * 64
    assert len(body["live_audit"]["runs"]) == 3
    stored = json.dumps(tasks.get(task_id))
    assert "sk-test-live-1234567890" not in stored


def test_plan_selection_writes_canonical_hash_and_requires_binding(
        client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload(client)
    _start(client, task_id, monkeypatch)
    response = client.post(f"/api/tasks/{task_id}/plan", json={"run_index": 2})
    assert response.status_code == 200, response.text
    selected = response.json()["selected_plan"]
    assert selected["canonical_sha256"] == CANONICAL
    assert selected["source"] == "live"
    assert Path(ROOT / selected["path"]).is_file()
    task = tasks.get(task_id)
    digest = task["review_binding_digest"]
    missing = client.post(f"/api/tasks/{task_id}/approve",
                          json={"expected_review_binding_digest": digest})
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "plan_not_approved"
    approved = client.post(f"/api/tasks/{task_id}/approve", json={
        "expected_review_binding_digest": digest,
        "expected_plan_sha256": CANONICAL, "reviewer_label": "M2-G4.1",
    })
    assert approved.status_code == 200
    assert approved.json().get("plan_sha256") == CANONICAL


def test_no_key_is_audit_no_provider(client: TestClient,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload(client)
    monkeypatch.setattr(assistant_key, "load_key", lambda: "")
    response = client.post(f"/api/tasks/{task_id}/audit/live", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "audit_no_provider"
    assert client.get(f"/api/tasks/{task_id}/audit").json()["audit_mode"] == "signed"


def test_unsupported_task_is_refused(client: TestClient,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = client.post("/api/tasks", json={"preview": True}).json()["id"]
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-live-1234567890")
    response = client.post(f"/api/tasks/{task_id}/audit/live", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "audit_unsupported"


def test_failed_child_marks_failed(client: TestClient,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload(client)
    live = _start(client, task_id, monkeypatch, _fake_spawn(returncode=2))
    assert live["status"] == "failed"
    assert live["error"] == "audit_failed"


def test_live_guest_choice_is_persisted(client: TestClient,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload(client)
    _start(client, task_id, monkeypatch)
    response = client.post(f"/api/tasks/{task_id}/audit/guest", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["live_guest"] is False
    assert client.get(f"/api/tasks/{task_id}/audit").json()["live_guest"] is False


def test_switch_back_to_signed_resets_live_selection(client: TestClient,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    task_id = _upload(client)
    _start(client, task_id, monkeypatch)
    selected = client.post(f"/api/tasks/{task_id}/plan", json={"run_index": 1})
    assert selected.status_code == 200
    response = client.post(f"/api/tasks/{task_id}/audit/signed")
    assert response.status_code == 200, response.text
    state = client.get(f"/api/tasks/{task_id}/audit").json()
    assert state["audit_mode"] == "signed"
    assert state["selected_plan"] is None
    task = tasks.get(task_id)
    assert task["approval"].get("approved") is False
    assert task["phase"] == "plans_ready"


def test_stale_running_state_recovers_instead_of_audit_running(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = _upload(client)
    _prepare_task(task_id, running=True)
    with live_audit._LOCK:
        live_audit._RUNNING.pop(task_id, None)
    live = _start(client, task_id, monkeypatch)
    assert live["status"] == "completed"
    assert len(live["runs"]) == 3


def test_reset_cancels_fanout_and_suppresses_late_writes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = _upload(client)
    processes: list[BlockingProcess] = []
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-live-1234567890")
    monkeypatch.setattr(live_audit, "_spawn", _blocking_spawn(processes))
    response = client.post(f"/api/tasks/{task_id}/audit/live", json={})
    assert response.status_code == 202
    assert len(processes) == 3
    _prepare_task(task_id, running=True)
    reset = client.post(f"/api/tasks/{task_id}/audit/signed")
    assert reset.status_code == 200
    assert all(process.terminated for process in processes)
    state = client.get(f"/api/tasks/{task_id}/audit").json()
    assert state["audit_mode"] == "signed"
    assert state["live_audit"]["status"] == "idle"
    assert state["selected_plan"] is None
    task = tasks.get(task_id)
    assert task["approval"] == {"approved": False}
    assert task["decision"] is None
    # A late watcher write must not resurrect live mode after reset.
    live_audit._set_state(task_id, {"status": "running", "runs": []})
    task = tasks.get(task_id)
    assert task["audit_mode"] == "signed"
    assert task["live_audit"]["status"] == "idle"


def test_reset_then_restart_clears_the_cancellation_flag(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = _upload(client)
    seen: list[BlockingProcess] = []
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-live-1234567890")
    monkeypatch.setattr(live_audit, "_spawn", _blocking_spawn(seen))
    assert client.post(f"/api/tasks/{task_id}/audit/live", json={}).status_code == 202
    assert client.post(f"/api/tasks/{task_id}/audit/signed").status_code == 200
    # Next attempt uses the normal fake child and must record completion.
    monkeypatch.setattr(live_audit, "_spawn", _fake_spawn())
    response = client.post(f"/api/tasks/{task_id}/audit/live", json={})
    assert response.status_code == 202
    live = live_audit.wait_for_terminal(task_id)
    assert live["status"] == "completed"
    assert len(live["runs"]) == 3


def test_invalid_generated_plan_reports_a_specific_reason() -> None:
    plan = {
        "edits": [
            {"kind": "redirect_call", "address": "0x1", "new_bytes": "e8 00 00 00 00"},
            {"kind": "guard_stub", "address": "0x2", "new_bytes": "90"},
        ]
    }
    selectable, reason = live_audit._plan_selectability(None, plan)
    assert selectable is False
    assert reason == "edit_kind_not_allowed:guard_stub"


def test_live_guest_is_disabled_off_windows(client: TestClient) -> None:
    task_id = _upload(client)
    if live_audit.GUEST_AVAILABLE:
        pytest.skip("WSL2 guest is available on this host")
    response = client.post(f"/api/tasks/{task_id}/audit/guest", json={"enabled": True})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "guest_unavailable"
    audit = client.get(f"/api/tasks/{task_id}/audit").json()
    assert audit["guest_available"] is False
    assert audit["live_guest"] is False
