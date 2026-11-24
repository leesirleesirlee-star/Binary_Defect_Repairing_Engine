"""G4.1 live mode backend tests with a fake audit child (no key, no WSL)."""

from __future__ import annotations

import base64
import json
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
        assert "--model" in command and "deepseek-v4-pro" in command
        assert env["DEEPSEEK_API_KEY"] == "sk-test-live-1234567890"
        summary_index = command.index("--summary-out") + 1
        summary_path = ROOT / command[summary_index]
        runs = []
        for index in range(1, 4):
            runs.append({
                "run_index": index,
                "schema_valid": True,
                "plan_sha256": f"{index:064x}",
                "plan_path": None,
                "plan": json.loads(PLAN.read_text(encoding="utf-8")),
                "usage": {"total_tokens": 100 + index},
            })
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps({"model": "deepseek-v4-pro", "runs": runs}),
                                encoding="utf-8")
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
    body = client.get(f"/api/tasks/{task_id}/audit").json()
    assert body["audit_mode"] == "live"
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
