#!/usr/bin/env python3
"""Record the x86-64 fixture manifest from the gcc-built artifact.

Runs on the Linux build host after build.sh. It does not build the ELF; the
compiler remains the provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from elftools.elf.elffile import ELFFile


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True, type=Path)
    ap.add_argument("--second-sha256", default="")
    args = ap.parse_args()
    root = args.fixture.resolve()
    source = root / "build" / "vuln.c"
    binary = root / "vuln.elf"
    cases = json.loads((root / "cases" / "cases.json").read_text(encoding="utf-8"))
    contract_path = root / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    with binary.open("rb") as fh:
        elf = ELFFile(fh)
        header = {
            "class": "ELF64" if elf.elfclass == 64 else f"ELF{elf.elfclass}",
            "machine": elf["e_machine"],
            "type": elf["e_type"],
            "entry": hex(elf["e_entry"]),
            "little_endian": elf.little_endian,
        }
        segments = []
        has_interp = False
        for seg in elf.iter_segments():
            if seg["p_type"] == "PT_INTERP":
                has_interp = True
            if seg["p_type"] == "PT_LOAD":
                flags = int(seg["p_flags"])
                segments.append({
                    "type": "PT_LOAD",
                    "vaddr": hex(seg["p_vaddr"]),
                    "filesz": seg["p_filesz"],
                    "memsz": seg["p_memsz"],
                    "flags": ("R" if flags & 4 else "-") + ("W" if flags & 2 else "-") + ("X" if flags & 1 else "-"),
                })
            if seg["p_type"] == "PT_GNU_STACK":
                flags = int(seg["p_flags"])
                segments.append({"type": "PT_GNU_STACK", "flags": ("R" if flags & 4 else "-") + ("W" if flags & 2 else "-") + ("X" if flags & 1 else "-")})
        symbols = {}
        symtab = elf.get_section_by_name(".symtab")
        if symtab:
            for sym in symtab.iter_symbols():
                if sym.name in {"handle", "main", "strcpy@plt", "puts@plt"}:
                    symbols[sym.name] = hex(sym["st_value"])
        needed = []
        dyn = elf.get_section_by_name(".dynamic")
        if dyn:
            for tag in dyn.iter_tags():
                if tag.entry.d_tag == "DT_NEEDED":
                    needed.append(tag.needed)
        if not symbols.get("handle"):
            raise SystemExit("missing handle symbol")

        text = elf.get_section_by_name(".text")
        start = int(symbols["handle"], 16)
        handle = next(s for s in symtab.iter_symbols() if s.name == "handle")
        # st_size can be 0 on some toolchains; slice to the end of .text.
        _ = handle
        code = text.data()[start - text["sh_addr"]:]
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        sub_rsp = None
        call_strcpy = None
        buf_off = None
        for insn in md.disasm(code, start):
            if insn.mnemonic == "sub" and insn.op_str.startswith("rsp,"):
                sub_rsp = int(insn.op_str.split(",")[1].strip(), 16)
            if insn.mnemonic == "call" and "strcpy" in insn.op_str:
                call_strcpy = {"address": hex(insn.address), "bytes": insn.bytes.hex(), "target": insn.op_str}
            m = re.search(r"\[rbp - (0x[0-9a-f]+)\]", insn.op_str)
            if m:
                buf_off = -int(m.group(1), 16)
        if sub_rsp is None or call_strcpy is None:
            raise SystemExit("could not recover handle frame / strcpy call")
        frame_method = "lea rbp displacement"
        if buf_off is None:
            # No parseable [rbp - X] addressing: derive the buffer location
            # from the frame size; still not a hardcoded offset.
            buf_off = -sub_rsp
            frame_method = "sub rsp size (no lea observed)"
        saved_rip_offset = 8 - buf_off
        frame = {
            "sub_rsp": hex(sub_rsp),
            "buf_rbp_offset": hex(buf_off),
            "saved_rip_offset": saved_rip_offset,
            "method": frame_method,
        }

    manifest = {
        "schema_version": 1,
        "fixture_id": "stack-overflow-01",
        "built_at": cmd("date", "-u", "+%Y-%m-%dT%H:%M:%SZ"),
        "toolchain": {
            "gcc": cmd("gcc", "--version").splitlines()[0],
            "ld": cmd("ld", "--version").splitlines()[0],
            "uname": cmd("uname", "-a"),
            "python": platform.python_version(),
        },
        "command": "gcc -O0 -g0 -fno-stack-protector -fno-pie -no-pie -fno-builtin -m64 -Wall -Wextra -Wl,-z,noexecstack -Wl,--build-id=none -o vuln.elf vuln.c",
        "source": {"path": "build/vuln.c", "sha256": sha(source)},
        "binary": {"path": "vuln.elf", "sha256": sha(binary), "size": binary.stat().st_size},
        "elf": header,
        "segments": segments,
        "has_interp": has_interp,
        "needed": needed,
        "symbols": symbols,
        "frame": frame,
        "strcpy_call": call_strcpy,
        "symbols_present": len(symbols) == 4,
        "reproducible": bool(args.second_sha256) and args.second_sha256 == sha(binary),
        "second_sha256": args.second_sha256,
        "cases": {"path": "cases/cases.json", "sha256": sha(root / "cases" / "cases.json")},
        "poc": {"path": "cases/poc.txt", "sha256": sha(root / "cases" / "poc.txt")},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    contract["binary_sha256"] = manifest["binary"]["sha256"]
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

    frozen = ["contract.json", "manifest.json", "vuln.elf", "build/build.sh", "build/vuln.c", "cases/cases.json", "cases/poc.txt"]
    lines = [f"{sha(root / rel)}  {rel}" for rel in frozen]
    (root / "SHA256SUMS").write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
