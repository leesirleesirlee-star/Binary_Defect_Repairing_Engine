"""Static contract tests for the M3 stack-overflow fixture.

These tests do not execute the ELF. Runtime behavior is checked by
``guest/run_cases.py`` inside the Linux guest.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "stack-overflow-01"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_elf_is_elf32_i386_exec() -> None:
    data = (FIXTURE / "vuln.elf").read_bytes()
    assert data[:4] == b"\x7fELF"
    assert data[4] == 1, "ELF32"
    assert data[5] == 1, "little-endian"
    assert struct.unpack_from("<H", data, 16)[0] == 2, "ET_EXEC"
    assert struct.unpack_from("<H", data, 18)[0] == 3, "EM_386"
    assert struct.unpack_from("<I", data, 24)[0] == 0x08048054
    phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize = struct.unpack_from("<H", data, 42)[0]
    phnum = struct.unpack_from("<H", data, 44)[0]
    assert phnum == 1
    p_type = struct.unpack_from("<I", data, phoff)[0]
    assert p_type == 1, "PT_LOAD"
    assert phentsize == 32


def test_elf_has_no_interpreter() -> None:
    data = (FIXTURE / "vuln.elf").read_bytes()
    phoff = struct.unpack_from("<I", data, 28)[0]
    phnum = struct.unpack_from("<H", data, 44)[0]
    types = [struct.unpack_from("<I", data, phoff + i * 32)[0] for i in range(phnum)]
    assert 3 not in types, "PT_INTERP must be absent (static, no PIE)"


def test_code_shape() -> None:
    data = (FIXTURE / "vuln.elf").read_bytes()
    code = data[0x54:]
    assert code.startswith(b"\xe8"), "entry must call vuln"
    assert b"\x83\xec\x20" in code, "sub esp, 32"
    assert b"\xba\x40\x00\x00\x00" in code, "read count 64"
    assert code.endswith(b"\xc9\xc3"), "leave; ret"


def test_manifest_and_contract_hashes() -> None:
    manifest = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))
    elf_sha = _sha(FIXTURE / "vuln.elf")
    assert manifest["binary"]["sha256"] == elf_sha
    assert contract["binary_sha256"] == elf_sha
    assert contract["frozen"] is True
    assert manifest["defect"]["buffer_bytes"] == 32
    assert manifest["defect"]["read_bytes"] == 64


def test_cases_are_hashed_and_bounded() -> None:
    contract = json.loads((FIXTURE / "contract.json").read_text(encoding="utf-8"))
    seen = set()
    for case in contract["cases"]:
        path = FIXTURE / case["path"]
        assert path.is_file(), case["path"]
        assert _sha(path) == case["sha256"], case["path"]
        assert len(path.read_bytes()) == case["length"]
        seen.add(case["path"])
        if case["kind"] == "valid":
            assert case["length"] <= 32
            if "exit_code" in case["expect"]:
                assert case["expect"]["exit_code"] == 0
        else:
            assert case["expect"]["signal"] == "SIGSEGV"
    assert "cases/poc.bin" in seen
    assert len((FIXTURE / "cases" / "poc.bin").read_bytes()) == 64


def test_reference_c_documents_the_same_defect() -> None:
    source = (FIXTURE / "build" / "vuln.c").read_text(encoding="utf-8")
    assert "char buf[32]" in source
    assert "sys_read(0, buf, 64)" in source
