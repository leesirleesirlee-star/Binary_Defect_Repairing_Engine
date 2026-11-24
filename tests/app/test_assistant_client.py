"""Real client seam tests: no key/token ever leaves the API host."""

from __future__ import annotations

from typing import Any

import pytest

from app import assistant, assistant_client, assistant_key


def test_client_returns_provider_content_without_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "sk-test-1234567890-secret"
    monkeypatch.setattr(assistant_key, "load_key", lambda: secret)
    monkeypatch.setattr(assistant_key, "chat_completion",
                        lambda messages, model=None, max_tokens=1600:
                        {"content": "hello from the provider", "model": "deepseek-chat"})
    result = assistant_client.complete([{"role": "user", "content": "hi"}])
    assert result == "hello from the provider"
    assert secret not in result


def test_client_without_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_key, "load_key", lambda: "")
    with pytest.raises(assistant_client.AssistantUnavailable) as error:
        assistant_client.complete([{"role": "user", "content": "hi"}])
    assert str(error.value) == "no_key"


def test_client_provider_failure_is_a_stable_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-1234567890-secret")

    def fail(messages: Any, model: Any = None, max_tokens: int = 1600) -> Any:
        raise assistant_key.KeyError("provider_unreachable")

    monkeypatch.setattr(assistant_key, "chat_completion", fail)
    with pytest.raises(assistant_client.AssistantUnavailable) as error:
        assistant_client.complete([{"role": "user", "content": "hi"}])
    assert str(error.value) == "provider_unreachable"


def test_client_never_returns_empty_provider_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-1234567890-secret")
    monkeypatch.setattr(assistant_key, "chat_completion",
                        lambda messages, model=None, max_tokens=1600: {"content": "  "})
    with pytest.raises(assistant_client.AssistantUnavailable) as error:
        assistant_client.complete([{"role": "user", "content": "hi"}])
    assert str(error.value) == "empty_provider_content"


def test_client_drops_unknown_model_action_chips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(assistant_key, "load_key", lambda: "sk-test-1234567890-secret")
    monkeypatch.setattr(assistant_key, "chat_completion",
                        lambda messages, model=None, max_tokens=1600: {"content":
                        '{"reply": "已结束。", "actions": ['
                        '{"id": "bad", "label_code": "primary", "kind": "primary"},'
                        '{"id": "ok", "label_code": "download", "kind": "download"}]}'})
    content = assistant_client.complete([{"role": "user", "content": "hi"}])
    assert assistant.validate_envelope(content) == {
        "reply": "已结束。",
        "actions": [{"id": "ok", "label_code": "download", "kind": "download"}],
    }
