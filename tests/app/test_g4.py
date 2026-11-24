"""G4 upload -> contracts -> repair tests for the console."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.journal import read_records
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01" / "vuln.elf"


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        session = test_client.get("/api/session")
        assert session.status_code == 200
        test_client.headers.update({"x-csrf-token": session.json()["csrf_token"]})
        yield test_client


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _upload(client: TestClient, binary: bytes) -> dict:
    valid = {"valid": ["", "A", "hello"]}
    poc = {"invalid": ["A" * 64]}
    payload = {
        "binary_name": "vuln.elf",
        "binary_base64": _b64(binary),
        "defect": "输入过长会导致崩溃",
        "case_files": [
            {"name": "regression.json", "content_base64": _b64(json.dumps(valid).encode("utf-8"))},
            {"name": "poc.json", "content_base64": _b64(json.dumps(poc).encode("utf-8"))},
        ],
    }
    return client.post("/api/tasks/upload", json=payload)


def _wait_run_end(client: TestClient, task_id: str) -> list[dict]:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        records = read_records(task_id)
        if records and records[-1]["type"] == "run_end":
            return records
        time.sleep(0.1)
    raise AssertionError("run did not end")


def test_fixture_upload_offers_three_contracts(client: TestClient) -> None:
    response = _upload(client, FIXTURE.read_bytes())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supported"] is True
    assert len(body["plans"]) == 3
    assert body["plans"][0]["feasible"] is True
    assert body["plans"][0]["strategy"] == "trampoline_guard"
    assert [item["feasible"] for item in body["plans"][1:]] == [False, False]
    assert body["analysis"]["function"] == "handle"
    assert body["analysis"]["cwe"] == "CWE-121"
    assert body["task"]["g4"]["cases"]["counts"] == {"valid": 3, "poc": 1, "total": 4}

    task_id = body["task"]["id"]
    g4 = client.get(f"/api/tasks/{task_id}/g4").json()
    assert g4["supported"] is True
    assert len(g4["options"]) == 3
    assert g4["selected_option"] is None


def test_select_contract_then_repair_end_to_end(client: TestClient) -> None:
    body = _upload(client, FIXTURE.read_bytes()).json()
    task_id = body["task"]["id"]
    select = client.post(f"/api/tasks/{task_id}/g4/select", json={"option_id": "guard_trampoline"})
    assert select.status_code == 200, select.text
    assert select.json()["option"]["strategy"] == "trampoline_guard"
    selected = select.json()["task"]
    assert selected["plan"] == "docs/audit/fix-plan-v1.json"

    digest = selected["review_binding_digest"]
    approved = client.post(
        f"/api/tasks/{task_id}/approve",
        json={"expected_review_binding_digest": digest, "reviewer_label": "M2-G4"},
    )
    assert approved.status_code == 200, approved.text
    decided = client.post(
        f"/api/tasks/{task_id}/decision", json={"request_id": "g4-select", "decision": "proceed"}
    )
    assert decided.status_code == 200, decided.text
    started = client.post(
        f"/api/tasks/{task_id}/start",
        json={"expected_review_binding_digest": digest},
        headers={"Idempotency-Key": "g4-test-" + task_id},
    )
    assert started.status_code == 200, started.text

    records = _wait_run_end(client, task_id)
    assert [record["type"] for record in records].count("run_end") == 1
    evaluation = [
        record
        for record in records
        if record["type"] == "verification" and record["payload"].get("kind") == "evaluation"
    ]
    assert evaluation
    assert evaluation[-1]["payload"]["verdict"] == "verified_against_stated_criteria"

    verdict = client.get(f"/api/tasks/{task_id}/verdict").json()
    assert verdict["available"] is True
    assert verdict["finalized"] is True
    assert verdict["verdict"] == "verified_against_stated_criteria"
    assert verdict["candidate_sha256"] == (
        "c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28"
    )

    journal = client.get(f"/api/tasks/{task_id}/journal").json()["records"]
    types = [record["type"] for record in journal]
    assert "plan_update" in types
    assert "command" in types and "verification" in types
    commands = [record for record in journal if record["type"] == "command"]
    assert any(record["payload"].get("phase") == "finished" for record in commands)

    artifacts = client.get(f"/api/tasks/{task_id}/artifacts").json()["artifacts"]
    names = {item["display_path"] for item in artifacts}
    assert {"candidate.elf", "edit-manifest.json", "verdict.json"} <= names
    candidate = next(item for item in artifacts if item["display_path"] == "candidate.elf")
    download = client.get(f"/api/artifacts/{candidate['artifact_id']}/download")
    assert download.status_code == 200
    assert download.content[:4] == b"\x7fELF"

    snapshot = client.get(f"/api/tasks/{task_id}").json()
    assert snapshot["g4"]["selected_option"] == "guard_trampoline"
    assert snapshot["decision"]["decision"] == "proceed"


def test_unimplementable_contract_is_refused(client: TestClient) -> None:
    body = _upload(client, FIXTURE.read_bytes()).json()
    task_id = body["task"]["id"]
    refused = client.post(
        f"/api/tasks/{task_id}/g4/select", json={"option_id": "inline_length_check"}
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "option_not_implementable"
    assert refused.json()["detail"]["reason_code"] == "insufficient_code_space"
    assert (
        "selected_option" not in client.get(f"/api/tasks/{task_id}/g4").json()
        or client.get(f"/api/tasks/{task_id}/g4").json()["selected_option"] is None
    )


def test_unknown_binary_is_analyzed_but_not_repaired(client: TestClient) -> None:
    response = _upload(client, FIXTURE.read_bytes() + b"\n")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supported"] is False
    assert all(not option["feasible"] for option in body["plans"])
    task_id = body["task"]["id"]
    refused = client.post(f"/api/tasks/{task_id}/g4/select", json={"option_id": "guard_trampoline"})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] in {
        "option_not_implementable",
        "unsupported_binary_scope",
    }


def test_upload_validation(client: TestClient) -> None:
    assert client.post("/api/tasks/upload", json={}).status_code == 422
    bad = client.post(
        "/api/tasks/upload", json={"binary_name": "x.bin", "binary_base64": _b64(b"not-an-elf")}
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "not_an_elf"


def test_fixture_payload_is_the_signed_demo(client: TestClient) -> None:
    response = client.get("/api/g4/fixture")
    assert response.status_code == 200, response.text
    body = response.json()
    binary = base64.b64decode(body["binary_base64"])
    assert binary == FIXTURE.read_bytes()
    assert body["sha256"] == body["sha256"].lower()
    assert len(body["case_files"]) == 2
    decoded = [json.loads(base64.b64decode(item["content_base64"])) for item in body["case_files"]]
    assert any(item.get("valid") for item in decoded)
    assert any(item.get("invalid") for item in decoded)


def test_elf_without_supported_finding_is_an_honest_scope_refusal(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import g4

    def no_finding(binary: Path, out_dir: Path) -> dict:
        return {
            "finding": None,
            "view": {"functions": []},
            "finding_sha256": None,
            "view_sha256": "0" * 64,
            "analysis_status": "no_supported_finding",
            "unsupported_detail": "no call to strcpy@plt found in the disassembly view",
        }

    monkeypatch.setattr(g4, "analyze_binary", no_finding)
    response = _upload(client, FIXTURE.read_bytes())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supported"] is False
    assert body["analysis_status"] == "no_supported_finding"
    assert body["analysis"]["status"] == "no_supported_finding"
    assert body["task"]["phase"] == "unsupported"
    assert [item["feasible"] for item in body["plans"]] == [False, False, False]
    assert body["task"]["g4"]["analysis_status"] == "no_supported_finding"
