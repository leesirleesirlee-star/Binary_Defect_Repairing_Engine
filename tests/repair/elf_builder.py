"""Build a small synthetic ELF64 image for M5 dry-run unit tests.

The image is intentionally *not* the real fixture and is never executed.  It has
the structural facts the repair tools need:

* one R-X PT_LOAD with a 0x1000-byte file-backed tail;
* a fake 5-byte ``call`` at 0x401194;
* a fake ``strcpy@plt`` target at 0x401060;
* a zero-filled reserved range starting at 0x401211;
* section headers, including ``.text`` ending at 0x401211.

The tests may modify a copy of these bytes to exercise negative cases.
"""

from __future__ import annotations

import struct
from pathlib import Path

PATCH_SITE_VADDR = 0x401194
STRCPY_PLT_VADDR = 0x401060
RESERVED_START = 0x401211
RESERVED_END = 0x402000
CAVE_VADDR = 0x401220
ENTRY_VADDR = 0x401090

ELF_HEADER_SIZE = 64
PROGRAM_HEADER_SIZE = 56
SECTION_HEADER_SIZE = 64
PHDR_OFFSET = 0x40
PHDR_COUNT = 3
SHDR_OFFSET = 0x3100
SHDR_COUNT = 4
SHSTRTAB_OFFSET = 0x3200
FILE_SIZE = 0x3300


def _elf_header() -> bytes:
    ident = b"\x7fELF\x02\x01\x01" + b"\x00" * 9
    return struct.pack(
        "<16sHHIQQQIHHHHHH",
        ident,
        2,  # ET_EXEC
        62,  # EM_X86_64
        1,  # EV_CURRENT
        ENTRY_VADDR,
        PHDR_OFFSET,
        SHDR_OFFSET,
        0,
        ELF_HEADER_SIZE,
        PROGRAM_HEADER_SIZE,
        PHDR_COUNT,
        SECTION_HEADER_SIZE,
        SHDR_COUNT,
        3,  # e_shstrndx -> .shstrtab
    )


def _program_header(
    p_type: int,
    p_flags: int,
    p_offset: int,
    p_vaddr: int,
    p_filesz: int,
    p_memsz: int,
    p_align: int = 0x1000,
) -> bytes:
    return struct.pack(
        "<IIQQQQQQ",
        p_type,
        p_flags,
        p_offset,
        p_vaddr,
        p_vaddr,
        p_filesz,
        p_memsz,
        p_align,
    )


def _section_header(
    name: int,
    sh_type: int,
    flags: int,
    addr: int,
    offset: int,
    size: int,
    align: int = 1,
) -> bytes:
    return struct.pack(
        "<IIQQQQIIQQ",
        name,
        sh_type,
        flags,
        addr,
        offset,
        size,
        0,
        0,
        align,
        0,
    )


def synthetic_elf_bytes(
    patch_site_vaddr: int = PATCH_SITE_VADDR,
    *,
    reserved_tail: bool = True,
) -> bytes:
    """Return a complete synthetic ELF64 image as bytes.

    ``patch_site_vaddr`` must keep the 5-byte call inside ``.text``.  Setting
    ``reserved_tail=False`` produces the pre-ADR 0x211-byte R-X segment so tests
    can verify the tools reject a fixture without a reserved tail.
    """
    if not 0x401000 <= patch_site_vaddr <= 0x40120C:
        raise ValueError("patch site must fit in .text before 0x401211")
    image = bytearray(FILE_SIZE)

    # ELF header and program headers.
    image[0:ELF_HEADER_SIZE] = _elf_header()
    rx_size = 0x1000 if reserved_tail else 0x211
    image[PHDR_OFFSET : PHDR_OFFSET + PROGRAM_HEADER_SIZE] = _program_header(
        1, 5, 0x1000, 0x401000, rx_size, rx_size
    )
    image[PHDR_OFFSET + PROGRAM_HEADER_SIZE : PHDR_OFFSET + 2 * PROGRAM_HEADER_SIZE] = (
        _program_header(1, 4, 0x2000, 0x402000, 0x100, 0x100)
    )
    image[PHDR_OFFSET + 2 * PROGRAM_HEADER_SIZE : PHDR_OFFSET + 3 * PROGRAM_HEADER_SIZE] = (
        _program_header(1, 6, 0x3000, 0x403000, 0x100, 0x100)
    )

    # .text: NOP-filled except for the fake call and a fake PLT stub.
    text = bytearray(b"\x90" * 0x211)
    text[0x60:0x66] = b"\xff\x25\x00\x00\x00\x00"
    site_offset = patch_site_vaddr - 0x401000
    call_rel32 = STRCPY_PLT_VADDR - (patch_site_vaddr + 5)
    text[site_offset : site_offset + 5] = b"\xe8" + struct.pack("<i", call_rel32)
    image[0x1000 : 0x1000 + len(text)] = text

    # .rodata in the second segment.
    image[0x2000:0x2010] = b"rodata\x00" + b"\x00" * 9

    # Section names and section header table.
    shstrtab = b"\x00.text\x00.rodata\x00.shstrtab\x00"
    image[SHSTRTAB_OFFSET : SHSTRTAB_OFFSET + len(shstrtab)] = shstrtab
    sections = b"".join(
        [
            _section_header(0, 0, 0, 0, 0, 0),
            _section_header(1, 1, 0x6, 0x401000, 0x1000, 0x211, 16),
            _section_header(7, 1, 0x2, 0x402000, 0x2000, 0x10),
            _section_header(15, 3, 0, 0, SHSTRTAB_OFFSET, len(shstrtab)),
        ]
    )
    image[SHDR_OFFSET : SHDR_OFFSET + len(sections)] = sections

    # Bytes 0x1211..0x2000 are left as zero by construction.  Assert the facts
    # the repair tests rely on so a builder bug fails loudly.
    if reserved_tail:
        assert image[RESERVED_START - 0x401000 : RESERVED_END - 0x401000] == b"\x00" * (
            RESERVED_END - RESERVED_START
        )
    patch_offset = 0x1000 + (patch_site_vaddr - 0x401000)
    assert image[patch_offset : patch_offset + 5] == b"\xe8" + struct.pack(
        "<i", STRCPY_PLT_VADDR - (patch_site_vaddr + 5)
    )
    return bytes(image)


def write_synthetic_elf(
    path: Path,
    *,
    patch_site_vaddr: int = PATCH_SITE_VADDR,
    reserved_tail: bool = True,
) -> Path:
    """Write the synthetic image to ``path`` and return the path."""
    path.write_bytes(
        synthetic_elf_bytes(
            patch_site_vaddr=patch_site_vaddr,
            reserved_tail=reserved_tail,
        )
    )
    return path
