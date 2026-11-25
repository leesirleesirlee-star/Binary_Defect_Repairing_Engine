"""Real DeepSeek-compatible chat client for the AI-hosted assistant.

The client seam is injected into ``app.api.ASSISTANT_CLIENT``.  It loads the
provider key inside the API host process, makes one chat-completions call via
``assistant_key`` (curl config file, never argv), and returns the raw assistant
content for ``assistant.respond`` to validate.  The key is never returned,
logged, or placed in a browser response; any failure is a stable exception that
the assistant maps to its deterministic fallback.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app import assistant, assistant_key


class AssistantUnavailable(RuntimeError):
    """Stable, non-secret reason the provider call could not be used."""


def complete(messages: Sequence[Mapping[str, str]], model: str | None = None) -> str:
    """Return one provider reply for the validated assistant message list."""
    if not assistant_key.load_key():
        raise AssistantUnavailable("no_key")
    try:
        result = assistant_key.chat_completion(
            [{"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
             for item in messages],
            model=model,
            max_tokens=3200,
        )
    except assistant_key.KeyError as error:
        raise AssistantUnavailable(str(error)) from error
    except Exception as error:  # provider/transport failures stay non-secret
        raise AssistantUnavailable("provider_failure") from error
    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise AssistantUnavailable("empty_provider_content")
    return _sanitize_actions(content)


def _sanitize_actions(content: str) -> str:
    """Keep a valid reply while dropping unsupported model action chips."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return content
    if not isinstance(payload, dict):
        return content
    reply = payload.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return content
    actions: list[dict[str, str]] = []
    raw_actions = payload.get("actions")
    for item in raw_actions if isinstance(raw_actions, list) else []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        label_code = item.get("label_code")
        action_id = item.get("id")
        if kind not in assistant.ACTION_KINDS:
            continue
        if not isinstance(label_code, str) or not label_code.strip():
            continue
        if not isinstance(action_id, str) or not action_id.strip():
            continue
        actions.append({"id": action_id[:64], "label_code": label_code[:64], "kind": kind})
    payload["actions"] = actions
    return json.dumps(payload, ensure_ascii=False)


def configured() -> dict[str, Any]:
    """Display-only provider state; never exposes the key."""
    return assistant_key.assistant_status()
