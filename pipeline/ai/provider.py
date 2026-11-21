"""DeepSeek chat-completions transport for the G2 audit.

The API key stays in the host process environment (``DEEPSEEK_API_KEY``); it is
never written to the prompt, report, repository or a log. Request and response
are hashed so every run is reproducible and auditable.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import jsonschema

from .prompt import build_prompt

_DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
_ROOT = Path(__file__).resolve().parents[2]
_FIXPLAN_SCHEMA = _ROOT / "schemas" / "FixPlanV1.schema.json"


class ProviderError(RuntimeError):
    """Raised when the provider call fails or the response is unusable."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_fixplan_schema() -> dict:
    """Return the frozen ``FixPlanV1`` schema."""
    return json.loads(_FIXPLAN_SCHEMA.read_text(encoding="utf-8"))


def call_chat(system: str, user: str, api_key: str, model: str, temperature: float = 0.0) -> dict:
    """Send one chat completion and return the raw provider response JSON."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    request = urllib.request.Request(
        _DEEPSEEK_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "binary-defect-repairing-engine/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"provider HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"provider unreachable: {exc.reason}") from exc


def _bind_identity(
    plan: dict,
    *,
    contract: dict,
    contract_sha256: str,
    fixture_id: str | None,
    plan_id: str | None,
    provider_name: str,
    model: str,
    prompt_sha256: str,
    response_sha256: str,
) -> dict:
    """Overwrite the identity fields with trusted values from the toolchain.

    The model cannot know the fixture id, the contract hash, the provider or the
    prompt hash, so it guesses. Binding is the runner's job, not the model's:
    every downstream consumer needs a plan that points at the frozen contract.
    """
    trusted_fixture = fixture_id or (
        contract.get("fixture_id") if isinstance(contract, dict) else None
    )
    if trusted_fixture:
        plan["fixture_id"] = trusted_fixture
    plan["contract_sha256"] = contract_sha256
    plan["plan_id"] = plan_id or ("plan-" + response_sha256[:12])
    plan["model"] = {
        "provider": provider_name,
        "name": model,
        "prompt_sha256": prompt_sha256,
    }
    return plan

def run_plan(
    contract: dict,
    view: dict,
    poc: dict,
    api_key: str | None = None,
    model: str | None = None,
    contract_sha256: str | None = None,
    fixture_id: str | None = None,
    plan_id: str | None = None,
    provider_name: str = "deepseek",
) -> dict:
    """Build the prompt, call the provider, validate FixPlanV1, return a record.

    The returned record carries the prompt and response hashes, the provider's
    model id and token usage, and a ``schema_valid`` flag. Invalid JSON or a plan
    that fails FixPlanV1 is recorded as ``schema_valid: False``, never retried
    silently here. A malformed provider response is a record, not an
    exception: the caller gets schema_valid False, plan None, raw None and a
    short error.
    """
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    model = model or os.environ.get("DEEPSEEK_MODEL")
    if not api_key:
        raise ProviderError("DEEPSEEK_API_KEY is not set")
    if not model:
        raise ProviderError("DEEPSEEK_MODEL is not set")
    if not contract_sha256:
        raise ProviderError("contract_sha256 is required to bind the plan")

    prompt = build_prompt(contract, view, poc)
    response = call_chat(prompt["system"], prompt["user"], api_key, model)

    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    if not isinstance(content, str):
        return {
            "prompt_sha256": prompt["prompt_sha256"],
            "response_sha256": None,
            "model": response.get("model") if isinstance(response, dict) else None,
            "usage": response.get("usage") if isinstance(response, dict) else None,
            "schema_valid": False,
            "plan": None,
            "raw": None,
            "error": "malformed provider response",
        }

    response_sha256 = _sha256(content)

    plan: dict | None = None
    schema_valid = False
    try:
        plan = json.loads(content)
        if isinstance(plan, dict):
            plan = _bind_identity(
                plan,
                contract=contract,
                contract_sha256=contract_sha256,
                fixture_id=fixture_id,
                plan_id=plan_id,
                provider_name=provider_name,
                model=model,
                prompt_sha256=prompt["prompt_sha256"],
                response_sha256=response_sha256,
            )
        jsonschema.validate(plan, load_fixplan_schema())
        schema_valid = True
    except (json.JSONDecodeError, jsonschema.ValidationError):
        schema_valid = False

    return {
        "prompt_sha256": prompt["prompt_sha256"],
        "response_sha256": response_sha256,
        "model": response.get("model"),
        "usage": response.get("usage"),
        "schema_valid": schema_valid,
        "plan": plan,
        "raw": content,
        "error": None,
    }
