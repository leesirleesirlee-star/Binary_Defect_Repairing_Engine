#!/usr/bin/env python3
"""ADR 0001 post-link step: reserve the R-X page tail.

The existing R-X PT_LOAD is extended to p_filesz = p_memsz = 0x1000, ending
exactly at the next PT_LOAD (vaddr 0x402000). No bytes are added or changed;
the tail already exists as zero fill in the file. This script asserts that the
tail is zero, unreferenced by sections, and that the next segment is unchanged.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PT_LOAD = 1
PF_X = 1
PF_R = 4
PAGE = 0x1000


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: reserve_tail.py <vuln.elf>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    data = bytearray(path.read_bytes())
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise SystemExit("expected ELF64 little-endian")

    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize = struct.unpack_from("<H", data, 54)[0]
    phnum = struct.unpack_from("<H", data, 56)[0]
    if phentsize != 56:
        raise SystemExit(f"unexpected program-header size {phentsize}")

    loads = []
    for i in range(phnum):
        off = phoff + i * phentsize
        fields = struct.unpack_from("<IIQQQQQQ", data, off)
        p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = fields
        if p_type == PT_LOAD:
            loads.append({
                "index": i, "off": off, "flags": p_flags, "offset": p_offset,
                "vaddr": p_vaddr, "filesz": p_filesz, "memsz": p_memsz,
            })

    exec_loads = [s for s in loads if (s["flags"] & PF_X) and (s["flags"] & PF_R)]
    if len(exec_loads) != 1:
        raise SystemExit(f"expected exactly one R-X PT_LOAD, got {len(exec_loads)}")
    seg = exec_loads[0]
    if seg["vaddr"] != 0x401000:
        raise SystemExit(f"unexpected R-X vaddr {seg['vaddr']:#x}")
    if seg["filesz"] != seg["memsz"]:
        raise SystemExit("R-X filesz/memsz already differ")

    tail_start = seg["vaddr"] + seg["filesz"]
    page_end = (seg["vaddr"] + PAGE) & ~(PAGE - 1)
    tail_size = page_end - tail_start
    if tail_size <= 0:
        raise SystemExit("no tail to reserve")

    next_loads = [s for s in loads if s["vaddr"] == page_end]
    if len(next_loads) != 1:
        raise SystemExit(f"expected next PT_LOAD at {page_end:#x}")
    nxt = next_loads[0]
    if nxt["offset"] != 0x2000:
        raise SystemExit(f"next PT_LOAD offset is {nxt['offset']:#x}, expected 0x2000")

    tail_off = seg["offset"] + (tail_start - seg["vaddr"])
    if tail_off + tail_size > len(data):
        raise SystemExit("file is shorter than the page tail")
    tail = data[tail_off:tail_off + tail_size]
    if any(tail):
        raise SystemExit("tail is not zero-filled")

    # No allocated section may overlap the reserved tail.
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shentsize = struct.unpack_from("<H", data, 58)[0]
    shnum = struct.unpack_from("<H", data, 60)[0]
    for i in range(shnum):
        off = shoff + i * shentsize
        sh_addr, sh_offset, sh_size = struct.unpack_from("<QQQ", data, off + 16)[:3]
        if sh_addr and sh_size:
            start, end = sh_addr, sh_addr + sh_size
            if start < page_end and end > tail_start:
                raise SystemExit(f"section {i} overlaps reserved tail: {start:#x}-{end:#x}")

    struct.pack_into("<Q", data, seg["off"] + 32, PAGE)
    struct.pack_into("<Q", data, seg["off"] + 40, PAGE)
    path.write_bytes(data)
    print(
        f"reserved tail {tail_start:#x}-{page_end:#x} "
        f"({tail_size:#x} bytes), R-X filesz=memsz=0x1000"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
