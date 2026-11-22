"""T3 tests: the chat assistant's honesty wall, fallback and envelope.

The chat assistant is chat text, never evidence: these tests lock the wall
between it and the audit model, the mode badge truth, the verbatim verdict
vocabulary and the deterministic fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import assistant
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
SUCCESS = "verified_against_stated_criteria"


def _record(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "payload": payload, "seq": 1, "version": 1}


def _frozen() -> list[dict[str, Any]]:
    return [
        _record(
            "corpus_update",
            {
                "fixture_id": "stack-overflow-01",
                "counts": {"valid": 5, "invalid": 4, "poc": 0},
                "total": 9,
                "cases_sha256": "fae5efd054358d16610987f5645eadc582ce53ac12debeb356941d6617ceec3d",
            },
        )
    ]


def _running() -> list[dict[str, Any]]:
    return _frozen() + [
        _record(
            "plan_update",
            {
                "revision": 1,
                "steps": [
                    {"step_id": step, "label_code": step, "status": status}
                    for step, status in zip(
                        (
                            "collect",
                            "freeze",
                            "analyze",
                            "audit",
                            "decision",
                            "repair",
                            "verify",
                            "export",
                        ),
                        (
                            "completed",
                            "completed",
                            "in_progress",
                            "pending",
                            "pending",
                            "pending",
                            "pending",
                            "pending",
                        ),
                        strict=True,
                    )
                ],
            },
        )
    ]


def test_intake_asks_for_the_binary_and_offers_the_attach_chip() -> None:
    envelope = assistant.respond({}, [], "你好", locale="zh-Hans")
    assert envelope["mode"] == assistant.MODE_DETERMINISTIC
    assert "程序" in envelope["reply"]
    assert envelope["actions"][0]["kind"] == "attach"
    assert all(word not in envelope["reply"] for word in assistant.VERDICT_WORDS)


def test_frozen_contract_quotes_only_persisted_counts_and_hash_prefix() -> None:
    envelope = assistant.respond({"id": "tsk_1"}, _frozen(), "开始", locale="zh-Hans")
    assert "9" in envelope["reply"]
    assert "fae5efd0" in envelope["reply"]
    assert envelope["actions"][0]["kind"] == "start"


def test_frozen_contract_without_values_does_not_invent_numbers() -> None:
    envelope = assistant.respond(
        {"id": "tsk_1"}, [_record("corpus_update", {})], "开始", locale="zh-Hans"
    )
    assert envelope["reply"] == assistant._TEXTS["zh-Hans"]["frozen_plain"]
    assert not any(char.isdigit() for char in envelope["reply"])


def test_running_progress_uses_the_plan_counts() -> None:
    envelope = assistant.respond({"id": "tsk_1"}, _running(), "进度", locale="zh-Hans")
    assert envelope["mode"] == assistant.MODE_DETERMINISTIC
    assert "2/8" in envelope["reply"]
    assert envelope["actions"] == []


def test_decision_quotes_persisted_audit_scores() -> None:
    records = _running() + [
        _record("audit_runs", {"report_sha256": None, "runs": [
            {"run_index": 1, "schema_valid": True, "score": 86,
             "critical_errors": [], "usable": True},
            {"run_index": 2, "schema_valid": True, "score": 74,
             "critical_errors": [], "usable": True},
            {"run_index": 3, "schema_valid": True, "score": 62,
             "critical_errors": [], "usable": True},
        ]}),
        _record(
            "awaiting_user",
            {"request_id": "req_1", "kind": "audit_decision",
             "allowed": ["proceed", "iterate", "change_scope"], "binding": {}},
        ),
    ]
    envelope = assistant.respond({"id": "tsk_1"}, records, "继续", locale="zh-Hans")
    assert "86 / 74 / 62" in envelope["reply"]
    assert "第 1 个" in envelope["reply"]
    kinds = [action["kind"] for action in envelope["actions"]]
    assert kinds == ["continue", "rerun"]


def test_decision_without_scores_says_so() -> None:
    records = _running() + [
        _record("audit_runs", {"runs": []}),
        _record("awaiting_user", {"request_id": "req_1", "kind": "audit_decision",
                                  "allowed": ["proceed", "iterate"], "binding": {}}),
    ]
    envelope = assistant.respond({"id": "tsk_1"}, records, "继续", locale="zh-Hans")
    assert "没有可用的评分" in envelope["reply"]
    assert envelope["reply"] == assistant._TEXTS["zh-Hans"]["audit_plain"]


def test_success_word_comes_only_from_a_persisted_verdict() -> None:
    task = {"id": "tsk_1", "verdict": {"verdict": SUCCESS}}
    artifacts = [{"path": "candidate.elf"}]
    envelope = assistant.respond(task, [], "结果", locale="zh-Hans", artifacts=artifacts)
    assert envelope["reply"] == assistant._TEXTS["zh-Hans"]["success"].format(word=SUCCESS)
    kinds = [action["kind"] for action in envelope["actions"]]
    assert kinds == ["download", "evidence"]


def test_missing_verdict_never_becomes_success() -> None:
    records = [
        _record("error", {"code": "stage_not_wired",
                          "correlation_id": "synthetic", "retry": {"kind": "manual"}}),
        _record(
            "run_end",
            {"execution": "failed", "ai": {"calls": None, "tokens": None, "cost_usd": None}},
        ),
    ]
    envelope = assistant.respond({"id": "tsk_1"}, records, "结果", locale="zh-Hans")
    assert SUCCESS not in envelope["reply"]
    assert "not_run" not in envelope["reply"]
    assert "stage_not_wired" in envelope["reply"]
    assert "/ui/#task/tsk_1" in envelope["reply"]
    kinds = [action["kind"] for action in envelope["actions"]]
    assert kinds == ["retry", "evidence"]


def test_failed_model_output_falls_back_without_echoing_provider_text() -> None:
    marker = "provider-secret-123"

    def broken(messages: Any) -> Any:
        return marker

    envelope = assistant.respond({}, [], "hello", client=broken)
    assert envelope["mode"] == assistant.MODE_DETERMINISTIC
    assert envelope["fallback_code"] == "assistant_fallback"
    assert marker not in envelope["reply"]


def test_raising_client_falls_back() -> None:
    def explode(messages: Any) -> Any:
        raise RuntimeError("provider exploded")

    envelope = assistant.respond({}, [], "hello", client=explode)
    assert envelope["mode"] == assistant.MODE_DETERMINISTIC
    assert "exploded" not in envelope["reply"]


def test_valid_model_output_is_used_and_marked_llm() -> None:
    def fake(messages: Any) -> Any:
        assert messages[0]["role"] == "system"
        return json.dumps(
            {"reply": "已收到，正在生成分析视图。",
             "actions": [{"id": "continue", "label_code": "continue", "kind": "continue"}]}
        )

    envelope = assistant.respond({"id": "tsk_1"}, [], "进度", client=fake)
    assert envelope["mode"] == assistant.MODE_LLM
    assert envelope["reply"] == "已收到，正在生成分析视图。"
    assert envelope["actions"] == [{"id": "continue", "label_code": "continue", "kind": "continue"}]


def test_model_cannot_quote_an_unpersisted_verdict() -> None:
    def fake(messages: Any) -> Any:
        return json.dumps({"reply": f"验证完成：{SUCCESS}", "actions": []})

    envelope = assistant.respond({}, [], "结果", client=fake)
    assert envelope["mode"] == assistant.MODE_DETERMINISTIC
    assert SUCCESS not in envelope["reply"]


def test_key_present_without_client_is_declared_not_wired() -> None:
    envelope = assistant.respond({}, [], "你好", key_present=True)
    assert envelope["mode"] == assistant.MODE_LLM_NOT_WIRED
    assert envelope["fallback_code"] == "assistant_llm_not_wired"


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"reply": "", "actions": []},
        {"reply": "ok", "actions": [{"id": "x", "label_code": "x", "kind": "delete_everything"}]},
        {"reply": "ok", "actions": [{"id": "x", "label_code": "", "kind": "start"}]},
        {"reply": "ok", "actions": {}},
        {"reply": "x" * (assistant.MAX_REPLY_CHARS + 1), "actions": []},
    ],
)
def test_validate_envelope_rejects_unexpected_model_output(value: Any) -> None:
    assert assistant.validate_envelope(value) is None


def test_validate_envelope_accepts_a_json_string() -> None:
    envelope = assistant.validate_envelope(
        '{"reply": "好的", "actions": [{"id": "start", "label_code": "start", "kind": "start"}]}'
    )
    assert envelope == {
        "reply": "好的",
        "actions": [{"id": "start", "label_code": "start", "kind": "start"}],
    }


def test_assistant_module_keeps_the_ai_wall() -> None:
    source = (ROOT / "app" / "assistant.py").read_text(encoding="utf-8")
    for forbidden in ("pipeline.", "urllib.request", "httpx", "requests", "http.client"):
        assert forbidden not in source


def test_english_locale_is_offered() -> None:
    envelope = assistant.respond({}, [], "hello", locale="en")
    assert envelope["reply"].startswith("Hello.")
    assert envelope["actions"][0]["kind"] == "attach"


# ---- API surface ---------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        session = test_client.get("/api/session")
        assert session.status_code == 200
        test_client.headers.update({"x-csrf-token": session.json()["csrf_token"]})
        yield test_client


def test_assistant_endpoint_serves_the_deterministic_fallback(client: TestClient) -> None:
    task_id = client.post("/api/tasks", json={"preview": True}).json()["id"]
    response = client.post(
        f"/api/tasks/{task_id}/assistant",
        json={"message": "开始", "locale": "zh-Hans"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == assistant.MODE_DETERMINISTIC
    assert isinstance(body["reply"], str) and body["reply"]
    assert isinstance(body["actions"], list)
    assert all(action["kind"] in assistant.ACTION_KINDS for action in body["actions"])


def test_assistant_endpoint_rejects_empty_messages(client: TestClient) -> None:
    task_id = client.post("/api/tasks", json={"preview": True}).json()["id"]
    response = client.post(f"/api/tasks/{task_id}/assistant", json={"message": ""})
    assert response.status_code in {401, 403, 422}
