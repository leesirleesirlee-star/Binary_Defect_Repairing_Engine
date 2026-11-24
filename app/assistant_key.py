"""Assistant provider key store and one small real connection test.

The key is accepted only over the local session, is never returned to the
browser, and is never written to logs.  On macOS/Linux it lives in a 0600 file
(the same ``BRKEY0`` format as the reference GUI, so an already configured key
keeps working).  The DeepSeek-compatible HTTP call is made with the host's
``curl`` through a private config file, so the key never appears in argv and no
network/urllib import is added to the GUI data layer.

This is an operator action only: no verdict, score or audit result is derived
from it, and a failed connection is reported as a stable code, never as a guess.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LEGACY_KEY = ROOT.parent / "binary-repair-gui" / "var" / "assistant.key"
MAGIC_PLAIN = b"BRKEY0\n"
MAX_KEY_LEN = 512
MIN_KEY_LEN = 16
KEY_ENVS = ("BINARYREPAIR_ASSISTANT_PROVIDER_KEY", "DEEPSEEK_API_KEY")
MODEL_ENVS = ("BINARYREPAIR_ASSISTANT_MODEL", "DEEPSEEK_MODEL")
BASE_ENVS = ("BINARYREPAIR_ASSISTANT_PROVIDER_BASE_URL", "DEEPSEEK_BASE_URL")
DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
FILE_ENV = "BINARYREPAIR_ASSISTANT_KEY_FILE"
_SAVE_LOCK = threading.Lock()


class KeyError(ValueError):
    """Key validation failure whose message is safe to show."""


def key_path() -> Path:
    override = (os.environ.get(FILE_ENV) or "").strip()
    if override:
        return Path(override)
    local = ROOT / "var" / "assistant.key"
    if not local.exists() and LEGACY_KEY.is_file():
        return LEGACY_KEY
    return local


def _env_key() -> str:
    for name in KEY_ENVS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _validate_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        raise KeyError("API key is empty.")
    if len(key) < MIN_KEY_LEN:
        raise KeyError("API key is too short.")
    if len(key) > MAX_KEY_LEN:
        raise KeyError("API key is too long.")
    if any(char.isspace() for char in key):
        raise KeyError("API key must not contain whitespace.")
    if any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise KeyError("API key must be printable ASCII.")
    return key


def load_key() -> str:
    env = _env_key()
    if env:
        return env
    path = key_path()
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    try:
        if raw.startswith(MAGIC_PLAIN):
            return base64.b64decode(raw[len(MAGIC_PLAIN) :]).decode("utf-8").strip()
        if raw.startswith(b"BRKEY1\n"):
            return ""
        return raw.decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError):
        return ""


def mask_key(key: str) -> str:
    if not key:
        return ""
    visible = 4 if len(key) > 8 else 0
    return "*" * (len(key) - visible) + key[-visible:]


def _write_key(path: Path, key: str) -> None:
    payload = MAGIC_PLAIN + base64.b64encode(key.encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(name)
    try:
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def save_key(raw_key: str) -> dict[str, Any]:
    if _env_key():
        raise KeyError("A provider key is already configured through the environment.")
    key = _validate_key(raw_key)
    with _SAVE_LOCK:
        _write_key(key_path(), key)
    return {"configured": True, "protection": "mode-0600"}


def clear_key() -> bool:
    if _env_key():
        raise KeyError("The provider key is managed by the environment.")
    path = key_path()
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def key_status() -> dict[str, Any]:
    env = _env_key()
    if env:
        return {
            "configured": True,
            "source": "environment",
            "masked": None,
            "can_clear": False,
            "protection": "environment",
        }
    key = load_key()
    if key:
        return {
            "configured": True,
            "source": "stored",
            "masked": mask_key(key),
            "can_clear": True,
            "protection": "mode-0600",
        }
    return {
        "configured": False,
        "source": None,
        "masked": None,
        "can_clear": False,
        "protection": None,
    }


def _first_env(names: tuple[str, ...], fallback: str = "") -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return fallback


def resolve_model(requested: Any = None) -> str:
    configured = _first_env(MODEL_ENVS)
    if configured:
        return configured
    return DEFAULT_MODEL


def _base_url() -> str:
    return _first_env(BASE_ENVS, DEFAULT_BASE).rstrip("/")


def _chat_body(messages: list[dict[str, str]], *, model: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }


def _curl_chat(messages: list[dict[str, str]], model: str, max_tokens: int) -> dict[str, Any]:
    """One POST through curl; the key travels in a 0600 config file, not argv."""
    key = load_key()
    if not key:
        raise KeyError("no_key")
    body = json.dumps(
        _chat_body(messages, model=model, max_tokens=max_tokens), ensure_ascii=False
    ).encode("utf-8")
    config = (
        'header = "Content-Type: application/json"\n'
        f'header = "Authorization: Bearer {key}"\n'
        "silent\n"
        "show-error\n"
    )
    fd, name = tempfile.mkstemp(prefix="assistant-curl-", suffix=".conf")
    config_path = Path(name)
    try:
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, OSError):
            pass
        os.write(fd, config.encode("utf-8"))
        os.close(fd)
        command = [
            "curl",
            "--max-time",
            "45",
            "--config",
            str(config_path),
            "--write-out",
            "\n%{http_code}",
            "--data-binary",
            "@-",
            _base_url() + "/chat/completions",
        ]
        try:
            result = subprocess.run(
                command, input=body, capture_output=True, timeout=60, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise KeyError("provider_unreachable") from error
    finally:
        try:
            config_path.unlink()
        except OSError:
            pass
    output = result.stdout.decode("utf-8", errors="replace")
    body_text, _, status_text = output.rpartition("\n")
    try:
        status = int(status_text.strip())
    except ValueError:
        status = 0
    if status == 0:
        raise KeyError("provider_unreachable")
    if status != 200:
        raise _ProviderHTTP(status)
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError as error:
        raise KeyError("malformed_provider_response") from error
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise KeyError("malformed_provider_response") from error
    if not isinstance(content, str) or not content.strip():
        raise KeyError("empty_provider_content")
    return {
        "content": content,
        "model": payload.get("model"),
        "usage": payload.get("usage"),
        "request_id": payload.get("id"),
    }


class _ProviderHTTP(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"provider_http_{status}")
        self.status = status


def chat_completion(messages: list[dict[str, str]], model: Any = None,
                    max_tokens: int = 1600) -> dict[str, Any]:
    """One chat-completions call for the assistant client seam.

    The key travels only in a 0600 curl config file; the returned dict never
    contains the key.  Exceptions are stable codes from ``_curl_chat``.
    """
    if not load_key():
        raise KeyError("no_key")
    return _curl_chat(messages, resolve_model(model), max_tokens)


def test_connection(model: Any = None) -> dict[str, Any]:
    """Make one tiny real provider call and return only non-secret diagnostics."""
    if not load_key():
        return {"ok": False, "error": "llm_client_not_configured"}
    resolved = resolve_model(model)
    try:
        result = _curl_chat(
            [
                {"role": "system", "content": "Reply with JSON only."},
                {"role": "user", "content": 'Return {"ok": true}.'},
            ],
            resolved,
            8,
        )
    except _ProviderHTTP as error:
        error_code = (
            "provider_rejected_key"
            if error.status in (401, 403)
            else f"provider_http_{error.status}"
        )
        return {"ok": False, "error": error_code}
    except KeyError as error:
        return {"ok": False, "error": str(error)}
    return {
        "ok": True,
        "requested_model": resolved,
        "model": result.get("model"),
        "request_id": result.get("request_id"),
        "usage": result.get("usage"),
    }


def chat_json(messages: list[dict[str, str]], *, model: Any = None, max_tokens: int = 600) -> str:
    """Assistant client seam: return the model content; never a verdict."""
    return _curl_chat(messages, resolve_model(model), max_tokens)["content"]


def assistant_status() -> dict[str, Any]:
    key = key_status()
    configured = bool(key["configured"])
    return {
        "mode": "llm" if configured else "deterministic",
        "model": resolve_model() if configured else None,
        "available": configured,
        "fallback_reason": None if configured else "no_client",
    }
