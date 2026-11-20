"""Tests for the source-free disassembly view (issue #7)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from pipeline.analyze import build_disassembly_view, build_finding

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01" / "vuln.elf"


@pytest.fixture(scope="module")
def view() -> dict:
    return build_disassembly_view(FIXTURE)


def test_view_locates_symbols_by_address(view: dict) -> None:
    assert view["elf"]["type"] == "ET_EXEC"
    assert view["elf"]["machine"] in {"x86-64", "EM_X86_64"}
    assert view["symbols"]["handle"] == "0x401176"
    assert view["symbols"]["main"] == "0x4011a8"
    assert view["plt"]["strcpy"] == "0x401060"
    assert view["plt"]["puts"] == "0x401070"


def test_view_contains_the_strcpy_call(view: dict) -> None:
    calls = [i for i in view["instructions"] if i["mnemonic"] == "call"]
    assert any(c["op_str"] == view["plt"]["strcpy"] for c in calls)


def test_view_has_no_source_material(view: dict) -> None:
    serialized = json.dumps(view)
    banned = [
        "fixtures/stack-overflow-01/build",
        "vuln.c",
        "#include",
        "strcpy(buf",
        "__attribute__",
        ".c\"",
    ]
    for marker in banned:
        assert marker not in serialized, f"source marker leaked: {marker!r}"


def test_view_has_no_dwarf_or_string_table(view: dict) -> None:
    names = {sec["name"] for sec in view["sections"]}
    assert not any(name.startswith(".debug") for name in names)
    assert ".symtab" not in names
    assert ".strtab" not in names


def test_finding_points_at_the_call(view: dict) -> None:
    finding = build_finding(view)
    assert finding["function"] == "handle"
    assert finding["address"] == "0x401194"
    assert finding["cwe"] == "CWE-121"
    assert finding["status"] == "confirmed_by_analysis"
    assert finding["frame"]["buf_rbp_offset"] == "-0x20"
    assert finding["frame"]["saved_rip_offset"] == 40


def test_emitted_documents_validate(view: dict) -> None:
    root = Path(__file__).resolve().parents[2] / "schemas"
    for name, doc in (("DisassemblyViewV1", view), ("FindingV1", build_finding(view))):
        schema = json.loads((root / f"{name}.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(doc, schema)
