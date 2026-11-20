"""S3 API/SSE tests: session, frozen contract, approval and labelled preview."""
from __future__ import annotations

import json
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
    # No real runner is wired: fail honestly, never fabricate a successful run.
    assert start.status_code == 503
    assert start.json()["detail"]["code"] == "runner_unavailable"


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
