#!/usr/bin/env python3
"""Build the M3 stack-overflow fixture as a minimal i386 Linux ELF32.

The artifact is intentionally freestanding: it uses only Linux i386 syscalls
(read/write/exit), so it runs on a 32-bit Linux guest without libc. It is not
meant to run on the Windows host.

Layout:
    _start -> call vuln -> exit(0)
    vuln   -> read(0, buf[32], 64); leave; ret

A 64-byte PoC overwrites the saved return address at buf+36. A valid input of
0..32 bytes returns normally.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

BASE = 0x08048000
EHDR_SIZE = 52
PHDR_SIZE = 32
CODE_OFFSET = EHDR_SIZE + PHDR_SIZE

# _start is at 0x08048000 + 0x54. vuln (push ebp) is at +0x62; call rel32 = 0x62 - 0x59.
CODE = bytes.fromhex(
    "e8 09 00 00 00"          # call vuln
    "b8 01 00 00 00"          # mov eax, 1 (exit)
    "31 db"                   # xor ebx, ebx
    "cd 80"                   # int 0x80
    "55"                      # push ebp
    "89 e5"                   # mov ebp, esp
    "83 ec 20"                # sub esp, 32
    "b8 03 00 00 00"          # mov eax, 3 (read)
    "31 db"                   # xor ebx, ebx (stdin)
    "89 e1"                   # mov ecx, esp
    "ba 40 00 00 00"          # mov edx, 64
    "cd 80"                   # int 0x80
    "c9"                      # leave
    "c3"                      # ret
)


def build() -> bytes:
    if len(CODE) != 0x26:
        raise AssertionError(f"unexpected code length: {len(CODE)}")
    ehdr = struct.pack(
        "<16sHHIIIIIHHHHHH",
        b"\x7fELF\x01\x01\x01" + b"\x00" * 9,
        2,                    # ET_EXEC
        3,                    # EM_386
        1,                    # EV_CURRENT
        BASE + CODE_OFFSET,   # e_entry
        EHDR_SIZE,            # e_phoff
        0,                    # e_shoff
        0,                    # e_flags
        EHDR_SIZE,            # e_ehsize
        PHDR_SIZE,            # e_phentsize
        1,                    # e_phnum
        40,                   # e_shentsize
        0,                    # e_shnum
        0,                    # e_shstrndx
    )
    phdr = struct.pack(
        "<IIIIIIII",
        1,                    # PT_LOAD
        0,                    # p_offset
        BASE,                 # p_vaddr
        BASE,                 # p_paddr
        CODE_OFFSET + len(CODE),
        0x1000,               # p_memsz
        7,                    # PF_R | PF_W | PF_X
        0x1000,               # p_align
    )
    return ehdr + phdr + CODE


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    payload = build()
    target = root / "vuln.elf"
    target.write_bytes(payload)
    print(f"wrote {target} ({len(payload)} bytes)")
    print(f"sha256 {hashlib.sha256(payload).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

