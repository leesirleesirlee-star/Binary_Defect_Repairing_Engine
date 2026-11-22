"""S3 API/SSE tests: session, frozen contract, approval and labelled preview."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.journal import read_records
from app.main import app
from app.preview_events import ensure_preview_journal

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        session = test_client.get("/api/session")
        assert session.status_code == 200
        test_client.headers.update({"x-csrf-token": session.json()["csrf_token"]})
        yield test_client


def _preview(client: TestClient) -> dict:
    response = client.post("/api/tasks", json={"preview": True})
    assert response.status_code == 201
    return response.json()


def test_session_cookie_and_contract_frozen(client: TestClient) -> None:
    task = _preview(client)
    contract = client.get(f"/api/tasks/{task['id']}/contract")
    assert contract.status_code == 200
    assert contract.json()["revision"] == 1
    update = client.put(
        f"/api/tasks/{task['id']}/contract",
        json={"expected_revision": 1, "contract": {}},
    )
    assert update.status_code == 409
    assert update.json()["detail"]["code"] == "frozen_contract"


def test_approval_binding_and_start_is_honest(client: TestClient) -> None:
    response = client.post("/api/tasks", json={})
    assert response.status_code == 201
    task_id = response.json()["id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    digest = task["review_binding_digest"]
    stale = client.post(f"/api/tasks/{task_id}/approve",
                        json={"expected_review_binding_digest": "0" * 64})
    assert stale.status_code == 409
    approved = client.post(f"/api/tasks/{task_id}/approve",
        json={"expected_review_binding_digest": digest, "reviewer_label": "test"})
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    start = client.post(f"/api/tasks/{task_id}/start",
                        json={"expected_review_binding_digest": digest},
                        headers={"Idempotency-Key": "test-key"})
    assert start.status_code == 200
    assert start.json()["run_id"].startswith("run_")
    replay = client.post(f"/api/tasks/{task_id}/start",
                         json={"expected_review_binding_digest": digest},
                         headers={"Idempotency-Key": "test-key"})
    assert replay.status_code == 200
    assert replay.json()["run_id"] == start.json()["run_id"]
    deadline = time.monotonic() + 60
    records = []
    while time.monotonic() < deadline:
        records = read_records(task_id)
        if records and records[-1]["type"] == "run_end":
            break
        time.sleep(0.1)
    assert records and records[-1]["type"] == "run_end"
    # The runner may stop at a not-yet-wired stage, but it must never fabricate success.
    assert records[-1]["payload"]["execution"] in {"failed", "cancelled"}
    terminal = client.get(f"/api/tasks/{task_id}").json()["execution"]
    assert terminal["terminal"] is True
    analysis = client.get(f"/api/tasks/{task_id}/analysis").json()
    assert analysis["available"] is True
    assert analysis["finding"]["status"] in {"hypothesis", "confirmed_by_analysis", "refuted"}
    artifacts = client.get(f"/api/tasks/{task_id}/artifacts").json()["artifacts"]
    assert {item["display_path"] for item in artifacts} >= {"disassembly.json", "finding.json"}
    download = client.get(artifacts[0]["download_url"])
    assert download.status_code == 200
    assert download.content
    bundle = client.get(f"/api/tasks/{task_id}/export").json()
    assert bundle["task"]["id"] == task_id
    assert bundle["verdict"] is None


def test_preview_journal_has_no_success(client: TestClient) -> None:
    task = _preview(client)
    ensure_preview_journal(task["id"])
    records = read_records(task["id"])
    assert records, "preview journal should be retained"
    assert all(record["source"] == "synthetic" for record in records)
    assert any(record["type"] == "corpus_update" for record in records)
    checks = [r for r in records
              if r["type"] == "verification" and r["payload"].get("kind") == "check"]
    assert checks and all(r["payload"]["status"] == "not_run" for r in checks)
    evaluations = [r for r in records if r["type"] == "verification"
                   and r["payload"].get("kind") == "evaluation"]
    assert evaluations and all(r["payload"]["verdict"] is None for r in evaluations)
    assert records[-1]["type"] == "run_end"
    assert records[-1]["payload"]["execution"] != "completed"


def test_sse_replay_stops_at_run_end(client: TestClient) -> None:
    task = _preview(client)
    with client.stream("GET", f"/api/tasks/{task['id']}/events") as response:
        assert response.status_code == 200
        lines = []
        for line in response.iter_lines():
            lines.append(line)
            if line.startswith("data: "):
                if json.loads(line[6:])["type"] == "run_end":
                    break
    data = [json.loads(line[5:]) for line in lines if line.startswith("data: ")]
    assert data
    assert data[-1]["type"] == "run_end"
    assert all(item["source"] == "synthetic" for item in data)

def test_sse_last_event_id_replays_after_sequence(client: TestClient) -> None:
    task = _preview(client)
    with client.stream("GET", f"/api/tasks/{task['id']}/events",
                       headers={"Last-Event-ID": "1"}) as response:
        assert response.status_code == 200
        data = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                item = json.loads(line[6:])
                data.append(item)
                if item["type"] == "run_end":
                    break
    assert data
    assert all(item["seq"] > 1 for item in data)
    assert data[0]["seq"] == 2

def test_decision_is_allowed_after_approval(client: TestClient) -> None:
    response = client.post("/api/tasks", json={})
    task_id = response.json()["id"]
    digest = client.get(f"/api/tasks/{task_id}").json()["review_binding_digest"]
    assert client.post(f"/api/tasks/{task_id}/decision",
                       json={"request_id": "r1", "decision": "proceed"}).status_code == 409
    client.post(f"/api/tasks/{task_id}/approve",
                json={"expected_review_binding_digest": digest, "reviewer_label": "test"})
    decision = client.post(f"/api/tasks/{task_id}/decision",
                           json={"request_id": "r1", "decision": "proceed"})
    assert decision.status_code == 200
    assert decision.json()["decision"] == "proceed"
    bad = client.post(f"/api/tasks/{task_id}/decision",
                      json={"request_id": "r2", "decision": "success"})
    assert bad.status_code == 422


def test_decision_is_persisted_in_the_task_snapshot(client: TestClient) -> None:
    task_id = client.post("/api/tasks", json={}).json()["id"]
    digest = client.get(f"/api/tasks/{task_id}").json()["review_binding_digest"]
    approved = client.post(
        f"/api/tasks/{task_id}/approve",
        json={"expected_review_binding_digest": digest, "reviewer_label": "test"},
    )
    assert approved.status_code == 200
    decided = client.post(
        f"/api/tasks/{task_id}/decision",
        json={"request_id": "req-1", "decision": "proceed"},
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["decision"] == "proceed"
    assert body["binding_digest"] == digest
    assert body["decided_at"].endswith("Z")

    snapshot = client.get(f"/api/tasks/{task_id}").json()
    record = snapshot["decision"]
    assert record["decision"] == "proceed"
    assert record["binding_digest"] == digest
    assert record["decided_at"] == body["decided_at"]

    journal = read_records(task_id)
    response = [item for item in journal if item["type"] == "user_response"][-1]
    assert response["payload"]["decision"] == "proceed"
    assert response["payload"]["binding_digest"] == digest
    assert response["payload"]["decided_at"] == body["decided_at"]


def test_unauthorized_decision_is_not_persisted(client: TestClient) -> None:
    task_id = client.post("/api/tasks", json={}).json()["id"]
    refused = client.post(
        f"/api/tasks/{task_id}/decision",
        json={"request_id": "req-1", "decision": "proceed"},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "approval_required"
    assert "decision" not in client.get(f"/api/tasks/{task_id}").json()

    digest = client.get(f"/api/tasks/{task_id}").json()["review_binding_digest"]
    client.post(
        f"/api/tasks/{task_id}/approve",
        json={"expected_review_binding_digest": digest, "reviewer_label": "test"},
    )
    invalid = client.post(
        f"/api/tasks/{task_id}/decision",
        json={"request_id": "req-1", "decision": "invent_success"},
    )
    assert invalid.status_code == 422
    assert "decision" not in client.get(f"/api/tasks/{task_id}").json()
