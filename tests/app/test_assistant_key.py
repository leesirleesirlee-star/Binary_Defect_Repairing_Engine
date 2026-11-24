"""Provider-key store and connection-test tests for the console settings."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import assistant_key
from app.main import app

KEY = "sk-test-0123456789abcdef"


@pytest.fixture()
def keyfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "assistant.key"
    monkeypatch.setenv(assistant_key.FILE_ENV, str(path))
    for name in (*assistant_key.KEY_ENVS, *assistant_key.MODEL_ENVS, *assistant_key.BASE_ENVS):
        monkeypatch.delenv(name, raising=False)
    return path


@pytest.fixture()
def client(keyfile: Path) -> TestClient:
    with TestClient(app) as test_client:
        session = test_client.get("/api/session")
        assert session.status_code == 200
        test_client.headers.update({"x-csrf-token": session.json()["csrf_token"]})
        yield test_client


def test_status_is_unconfigured_until_a_key_is_saved(client: TestClient, keyfile: Path) -> None:
    status = client.get("/api/assistant/key").json()
    assert status["key"]["configured"] is False
    assert status["key"]["can_clear"] is False
    assert status["assistant"]["mode"] == "deterministic"


def test_save_masks_and_never_echoes_the_key(client: TestClient, keyfile: Path) -> None:
    missing = client.post("/api/assistant/key", json={})
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "key_required"

    short = client.post("/api/assistant/key", json={"key": "short"})
    assert short.status_code == 422
    assert short.json()["detail"]["code"] == "key_rejected"

    saved = client.post("/api/assistant/key", json={"key": KEY})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["key"]["configured"] is True
    assert body["key"]["source"] == "stored"
    assert body["key"]["can_clear"] is True
    assert KEY not in json.dumps(body)
    assert KEY not in json.dumps(client.get("/api/assistant/key").json())
    raw = keyfile.read_bytes()
    assert KEY.encode() not in raw
    assert oct(keyfile.stat().st_mode & 0o777) == "0o600"

    cleared = client.delete("/api/assistant/key")
    assert cleared.status_code == 200
    assert cleared.json()["key"]["configured"] is False
    assert not keyfile.exists()


def test_environment_key_wins_and_cannot_be_cleared(
    client: TestClient, keyfile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-0123456789abcdef")
    status = client.get("/api/assistant/key").json()
    assert status["key"]["source"] == "environment"
    assert status["key"]["can_clear"] is False
    assert client.post("/api/assistant/key/test", json={}).status_code == 200
    refused = client.delete("/api/assistant/key")
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "key_managed"


def test_connection_test_without_key_is_explicit(client: TestClient) -> None:
    result = client.post("/api/assistant/key/test", json={}).json()
    assert result == {"ok": False, "error": "llm_client_not_configured"}


def test_connection_test_maps_provider_errors(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/api/assistant/key", json={"key": KEY}).status_code == 200

    def unauthorized(messages, model, max_tokens):
        raise assistant_key._ProviderHTTP(401)

    monkeypatch.setattr(assistant_key, "_curl_chat", unauthorized)
    result = client.post("/api/assistant/key/test", json={}).json()
    assert result == {"ok": False, "error": "provider_rejected_key"}


def test_connection_test_success_returns_provider_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/api/assistant/key", json={"key": KEY}).status_code == 200

    def ok(messages, model, max_tokens):
        assert max_tokens == 64
        return {
            "content": '{"ok": true}',
            "model": "deepseek-chat",
            "usage": {"prompt_tokens": 2, "completion_tokens": 2},
            "request_id": "req_1",
        }

    monkeypatch.setattr(assistant_key, "_curl_chat", ok)
    result = client.post("/api/assistant/key/test", json={}).json()
    assert result["ok"] is True
    assert result["model"] == "deepseek-chat"
    assert result["request_id"] == "req_1"


def test_curl_call_never_puts_the_key_in_argv(
    keyfile: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assistant_key.save_key(KEY)
    seen: dict[str, object] = {}

    def fake_run(command, input, capture_output, timeout, check):  # noqa: A002
        seen["command"] = list(command)
        config_path = Path(command[4])
        seen["config"] = config_path.read_text(encoding="utf-8")
        seen["body"] = json.loads(input)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b'{"id":"req_1","model":"deepseek-chat","choices":[{"message":{"content":"{\\"ok\\":true}"}}]}\n200',
            stderr=b"",
        )

    monkeypatch.setattr(assistant_key.subprocess, "run", fake_run)
    result = assistant_key._curl_chat([{"role": "user", "content": "ping"}], "deepseek-chat", 8)
    assert result["content"] == '{"ok":true}'
    assert KEY not in " ".join(str(item) for item in seen["command"])
    assert f"Authorization: Bearer {KEY}" in str(seen["config"])
    assert not Path(str(seen["command"][4])).exists()


def test_legacy_key_file_is_read_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "assistant.key"
    import base64

    legacy.write_bytes(assistant_key.MAGIC_PLAIN + base64.b64encode(KEY.encode("utf-8")))
    monkeypatch.setenv(assistant_key.FILE_ENV, str(legacy))
    assert assistant_key.load_key() == KEY
    assert assistant_key.key_status()["source"] == "stored"


def test_explicit_model_selection_overrides_the_provider_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    assert assistant_key.resolve_model("deepseek-v4-pro") == "deepseek-v4-pro"
    assert assistant_key.resolve_model("deepseek-flash") == "deepseek-flash"
    assert assistant_key.resolve_model(None) == "deepseek-chat"
    assert assistant_key.resolve_model("default") == "deepseek-chat"


def test_connection_test_sends_the_explicitly_selected_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/api/assistant/key", json={"key": KEY}).status_code == 200
    seen: dict[str, str] = {}

    def ok(messages, model, max_tokens):
        seen["model"] = model
        return {"content": '{"ok": true}', "model": "deepseek-flash",
                "usage": {}, "request_id": "req_2"}

    monkeypatch.setattr(assistant_key, "_curl_chat", ok)
    result = client.post("/api/assistant/key/test",
                         json={"model": "deepseek-v4-pro"}).json()
    assert result["ok"] is True
    assert seen["model"] == "deepseek-v4-pro"
    assert result["requested_model"] == "deepseek-v4-pro"
    assert result["model"] == "deepseek-flash"
