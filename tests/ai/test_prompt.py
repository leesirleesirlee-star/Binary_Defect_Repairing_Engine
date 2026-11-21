"""Tests for the G2 prompt builder and provider transport (issue #8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest

from pipeline.ai.prompt import DEFECT_DESCRIPTION, build_prompt, load_system_prompt
from pipeline.ai.provider import ProviderError, run_plan
from pipeline.analyze import build_disassembly_view

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01" / "vuln.elf"
CONTRACT = json.loads(
    (ROOT / "fixtures" / "stack-overflow-01" / "contract.json").read_text(encoding="utf-8")
)
POC = {"input": "A" * 64, "observed_output": {"signal": "SIGSEGV"}}
CONTRACT_SHA = hashlib.sha256(
    (ROOT / "fixtures" / "stack-overflow-01" / "contract.json").read_bytes()
).hexdigest()


@pytest.fixture(scope="module")
def prompt() -> dict:
    view = build_disassembly_view(FIXTURE)
    return build_prompt(CONTRACT, view, POC)


def test_system_prompt_has_no_source(prompt: dict) -> None:
    for marker in ("vuln.c", "#include", "__attribute__", "build/", "fixtures/"):
        assert marker not in prompt["system"]
    assert "32-byte stack buffer" in DEFECT_DESCRIPTION


def test_prompt_has_no_source(prompt: dict) -> None:
    for marker in ("vuln.c", "#include", "__attribute__", "fixtures/", "build/"):
        assert marker not in prompt["user"]


def test_prompt_rejects_a_source_path() -> None:
    view = build_disassembly_view(FIXTURE)
    view["elf"]["sha256"] = "fixtures/stack-overflow-01/build/vuln.c"
    with pytest.raises(ValueError, match="source material"):
        build_prompt(CONTRACT, view, POC)


def test_prompt_hash_is_deterministic() -> None:
    view = build_disassembly_view(FIXTURE)
    a = build_prompt(CONTRACT, view, POC)
    b = build_prompt(CONTRACT, view, POC)
    assert a["prompt_sha256"] == b["prompt_sha256"]
    assert len(a["prompt_sha256"]) == 64


def test_system_prompt_is_versioned_file() -> None:
    assert load_system_prompt().startswith("You are a binary security analyst.")


def test_run_plan_rejects_invalid_fixplan() -> None:
    view = build_disassembly_view(FIXTURE)
    fake_plan = {"schema_version": 1}
    raw = json.dumps(
        {
            "choices": [{"message": {"content": json.dumps(fake_plan)}}],
            "model": "deepseek-chat",
            "usage": {"total_tokens": 1},
        }
    )
    with mock.patch("pipeline.ai.provider.call_chat", return_value=json.loads(raw)):
        record = run_plan(
            CONTRACT,
            view,
            POC,
            api_key="x",
            model="deepseek-chat",
            contract_sha256=CONTRACT_SHA,
        )
    assert record["schema_valid"] is False
    assert record["plan"] is not None
    assert record["plan"]["contract_sha256"] == CONTRACT_SHA
    assert len(record["response_sha256"]) == 64


def test_run_plan_requires_key_and_model() -> None:
    view = build_disassembly_view(FIXTURE)
    with mock.patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
            run_plan(CONTRACT, view, POC)


def test_run_plan_records_a_malformed_provider_response() -> None:
    view = build_disassembly_view(FIXTURE)
    bodies = (
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": 42}}]},
    )
    for body in bodies:
        with mock.patch("pipeline.ai.provider.call_chat", return_value=body):
            record = run_plan(
                CONTRACT,
                view,
                POC,
                api_key="x",
                model="deepseek-chat",
                contract_sha256=CONTRACT_SHA,
            )
        assert record["schema_valid"] is False
        assert record["plan"] is None
        assert record["response_sha256"] is None
        assert record["raw"] is None
        assert record["error"] == "malformed provider response"


def test_run_plan_binds_trusted_identity() -> None:
    view = build_disassembly_view(FIXTURE)
    model_plan = {
        "schema_version": 1,
        "plan_id": "model-invented",
        "fixture_id": "wrong-fixture",
        "contract_sha256": "0" * 64,
        "model": {"provider": "unknown", "name": "unknown", "prompt_sha256": "0" * 64},
        "diagnosis": {
            "function": "handle",
            "address": "0x401194",
            "instruction": "call strcpy@plt",
            "cwe": "CWE-121",
            "confidence": 0.9,
            "evidence": ["call site"],
        },
        "root_cause": "unbounded copy",
        "strategy": "trampoline_guard",
        "edits": [
            {
                "kind": "redirect_call",
                "address": "0x401194",
                "original_bytes": "e8 c7 fe ff ff",
                "new_bytes": "e8 87 00 00 00",
            }
        ],
        "stub": {"language": "asm", "source": "length check", "estimated_size_bytes": 69},
        "valid_path": "unchanged",
        "invalid_path": "rejected",
        "stated_criteria_coverage": [{"criterion": "c", "how": "h"}],
        "assumptions": [],
        "uncertainties": [],
        "verification_proposal": ["PoC"],
    }
    body = {"choices": [{"message": {"content": json.dumps(model_plan)}}], "model": "deepseek-chat"}
    with mock.patch("pipeline.ai.provider.call_chat", return_value=body):
        record = run_plan(
            CONTRACT,
            view,
            POC,
            api_key="x",
            model="deepseek-chat",
            contract_sha256=CONTRACT_SHA,
            fixture_id="stack-overflow-01",
        )
    plan = record["plan"]
    assert record["schema_valid"] is True
    assert plan["fixture_id"] == "stack-overflow-01"
    assert plan["contract_sha256"] == CONTRACT_SHA
    assert plan["model"]["prompt_sha256"] == record["prompt_sha256"]
    assert plan["model"]["name"] == "deepseek-chat"
