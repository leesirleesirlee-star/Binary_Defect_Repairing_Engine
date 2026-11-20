"""Static contract tests for the x86-64 stack-overflow fixture.

These tests never execute the ELF. Runtime behavior belongs to
guest/run_cases.py inside the Linux guest.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _elf():
    fh = (FIXTURE / "vuln.elf").open("rb")
    return fh, ELFFile(fh)


def test_elf_header_and_interp() -> None:
    fh, elf = _elf()
    try:
        assert elf.elfclass == 64
        assert elf["e_machine"] == "EM_X86_64"
        assert elf["e_type"] == "ET_EXEC"
        assert elf.little_endian is True
        segs = list(elf.iter_segments())
        assert any(seg["p_type"] == "PT_INTERP" for seg in segs)
        assert any(seg["p_type"] == "PT_GNU_STACK" for seg in segs)
        for seg in segs:
            if seg["p_type"] == "PT_LOAD":
                flags = int(seg["p_flags"])
                assert not (flags & 1 and flags & 2), "LOAD must not be W+X"
        assert elf.get_section_by_name(".dynamic") is not None
    finally:
        fh.close()


def test_symbols_and_no_stack_chk() -> None:
    fh, elf = _elf()
    try:
        symtab = elf.get_section_by_name(".symtab")
        names = {sym.name for sym in symtab.iter_symbols()}
        assert {"handle", "main", "strcpy@plt", "puts@plt"} <= names
        assert not any("stack_chk" in name for name in names)
        dynamic = elf.get_section_by_name(".dynamic")
        needed = [tag.needed for tag in dynamic.iter_tags() if tag.entry.d_tag == "DT_NEEDED"]
        assert any("libc.so.6" in item for item in needed)
    finally:
        fh.close()


def test_handle_calls_strcpy_plt() -> None:
    fh, elf = _elf()
    try:
        symtab = elf.get_section_by_name(".symtab")
        symbols = {sym.name: sym for sym in symtab.iter_symbols()}
        handle = symbols["handle"]
        text = elf.get_section_by_name(".text")
        code = text.data()[handle["st_value"] - text["sh_addr"]: handle["st_value"] - text["sh_addr"] + handle["st_size"]]
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        instructions = list(md.disasm(code, handle["st_value"]))
        assert any(insn.mnemonic == "sub" and insn.op_str.startswith("rsp,") for insn in instructions)
        manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
        calls = [insn for insn in instructions if insn.mnemonic == "call"]
        assert len(calls) >= 2, "handle must call strcpy@plt then puts@plt"
        assert all(len(insn.bytes) == 5 for insn in calls)
        assert calls[0].op_str == manifest["symbols"]["strcpy@plt"]
        assert calls[1].op_str == manifest["symbols"]["puts@plt"]
    finally:
        fh.close()


def test_manifest_contract_and_cases() -> None:
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))
    corpus = json.loads((FIXTURE / "cases" / "cases.json").read_text(encoding="utf-8"))
    assert manifest["binary"]["sha256"] == _sha(FIXTURE / "vuln.elf")
    assert contract["binary_sha256"] == manifest["binary"]["sha256"]
    assert manifest["symbols_present"] is True
    # Derive the return-address offset from the recorded frame, not a constant.
    buf_offset = int(manifest["frame"]["buf_rbp_offset"], 16)
    assert manifest["frame"]["saved_rip_offset"] == 8 - buf_offset
    assert manifest["reproducible"] is True
    valid = [case for case in corpus["cases"] if case["kind"] == "valid"]
    invalid = [case for case in corpus["cases"] if case["kind"] == "invalid"]
    assert len(valid) == 5 and len(invalid) == 4
    assert all(len(case["argv"][0]) <= 31 for case in valid)
    assert all(len(case["argv"][0]) >= 32 for case in invalid)
    assert all(case["expected_candidate"]["stderr"] == contract["stated_criteria"]["invalid_stderr"] for case in invalid)
    assert (FIXTURE / "cases" / "poc.txt").read_bytes() == b"A" * 64


def test_source_is_build_only_and_quarantined() -> None:
    source = (FIXTURE / "build" / "vuln.c").read_text(encoding="utf-8")
    assert source.startswith("/* BUILD-ONLY.")
    assert "__attribute__((noinline))" in source
    assert "static void handle(char *input)" in source
    assert "char buf[32]" in source
    assert "strcpy(buf, input)" in source
    assert "puts(buf)" in source
