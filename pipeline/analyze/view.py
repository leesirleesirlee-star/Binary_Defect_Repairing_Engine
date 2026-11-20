"""Build a source-free ``DisassemblyViewV1`` from the frozen fixture ELF.

Deterministic and source-free: it reads only the binary bytes, never the build
directory or the C source. The output is the only binary material the model may
see, so it must contain no source path, no DWARF line table and no source text.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from elftools.elf.elffile import ELFFile

_FUNC_SYMBOLS = {"handle", "main"}
_PLT_SYMBOLS = {"strcpy@plt", "puts@plt"}


def _hex(value: int) -> str:
    return hex(value)


def _section_flags(flags: int) -> str:
    """Render SHF_* bits as a short W/A/X string (readelf-style order)."""
    out = ""
    if flags & 0x1:  # SHF_WRITE
        out += "W"
    if flags & 0x2:  # SHF_ALLOC
        out += "A"
    if flags & 0x4:  # SHF_EXECINSTR
        out += "X"
    return out


def _disassemble(data: bytes, base: int) -> list[dict]:
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    out: list[dict] = []
    for insn in md.disasm(data, base):
        out.append(
            {
                "address": hex(insn.address),
                "bytes": " ".join(f"{byte:02x}" for byte in insn.bytes),
                "mnemonic": insn.mnemonic,
                "op_str": insn.op_str,
            }
        )
    return out


def build_disassembly_view(elf_path: str | Path) -> dict:
    """Return a ``DisassemblyViewV1`` document for ``elf_path``."""
    path = Path(elf_path)
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()

    with path.open("rb") as fh:
        elf = ELFFile(fh)

        view: dict = {
            "schema_version": 1,
            "elf": {
                "sha256": sha256,
                "class": "ELF64" if elf.elfclass == 64 else f"ELF{elf.elfclass}",
                "machine": elf["e_machine"],
                "type": elf["e_type"],
                "entry": hex(elf["e_entry"]),
                "pie": elf["e_type"] == "ET_DYN",
            },
            "segments": [],
            "symbols": {},
            "instructions": [],
            "plt": {},
            "sections": [],
        }

        # Load segments only.
        for seg in elf.iter_segments():
            if seg["p_type"] != "PT_LOAD":
                continue
            flags = int(seg["p_flags"])
            view["segments"].append(
                {
                    "type": "PT_LOAD",
                    "vaddr": hex(seg["p_vaddr"]),
                    "filesz": seg["p_filesz"],
                    "memsz": seg["p_memsz"],
                    "flags": (
                        ("R" if flags & 4 else "-")
                        + ("W" if flags & 2 else "-")
                        + ("X" if flags & 1 else "-")
                    ),
                }
            )

        # Allocated sections with a name (never .symtab/.strtab/debug, which have
        # sh_addr == 0 and can carry the source file name).
        for sec in elf.iter_sections():
            if sec["sh_addr"] and sec.name:
                view["sections"].append(
                    {
                        "name": sec.name,
                        "vaddr": hex(sec["sh_addr"]),
                        "size": sec["sh_size"],
                        "flags": _section_flags(int(sec["sh_flags"])),
                    }
                )

        # Symbols: the target function, main, and the PLT stubs it calls.
        symtab = elf.get_section_by_name(".symtab")
        funcs: dict[str, tuple[int, int]] = {}
        if symtab is not None:
            for sym in symtab.iter_symbols():
                name = sym.name
                if name in _FUNC_SYMBOLS and sym["st_info"]["type"] == "STT_FUNC":
                    addr = sym["st_value"]
                    funcs[name] = (addr, sym["st_size"])
                    view["symbols"][name] = hex(addr)
                elif name in _PLT_SYMBOLS:
                    view["symbols"][name] = hex(sym["st_value"])
                    view["plt"][name[: -len("@plt")]] = hex(sym["st_value"])

        # Disassemble handle + main from .text, then the PLT stubs.
        instructions: list[dict] = []
        text = elf.get_section_by_name(".text")
        if text is not None:
            data = text.data()
            base = text["sh_addr"]
            for addr, size in sorted(funcs.values()):
                if 0 < size and base <= addr < base + len(data):
                    off = addr - base
                    instructions.extend(_disassemble(data[off : off + size], addr))
        pltsec = elf.get_section_by_name(".plt.sec") or elf.get_section_by_name(".plt")
        if pltsec is not None:
            instructions.extend(_disassemble(pltsec.data(), pltsec["sh_addr"]))

        seen: dict[int, dict] = {}
        for insn in instructions:
            seen[int(insn["address"], 16)] = insn
        view["instructions"] = [seen[addr] for addr in sorted(seen)]

        return view
