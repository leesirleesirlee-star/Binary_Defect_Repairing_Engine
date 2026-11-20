"""Tests for the pure-Python ELF64 reader and dry-run editor."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.repair.elf64 import ELF64, PF_R, PF_X, Edit, ELFError, align_up, fits_rel32
from tests.repair.elf_builder import (
    PATCH_SITE_VADDR,
    STRCPY_PLT_VADDR,
    synthetic_elf_bytes,
    write_synthetic_elf,
)


@pytest.fixture()
def elf_path(tmp_path: Path) -> Path:
    """Create a synthetic ELF64 on disk for one test."""
    return write_synthetic_elf(tmp_path / "synthetic.elf")


def test_parse_headers_segments_and_sections(elf_path: Path) -> None:
    """The parser recovers the header facts needed by the repair tools."""
    elf = ELF64.from_path(elf_path)
    assert elf.e_type == 2  # ET_EXEC
    assert elf.e_machine == 62  # EM_X86_64
    assert elf.e_entry == 0x401090
    assert len(elf.pt_load_segments()) == 3
    assert elf.executable_load_segments()[0].executable
    assert elf.executable_load_segments()[0].p_flags == PF_X | PF_R
    assert [section.name for section in elf.sections] == [
        "",
        ".text",
        ".rodata",
        ".shstrtab",
    ]


def test_vaddr_offset_roundtrip_and_read(elf_path: Path) -> None:
    """Virtual addresses map to file offsets and back without loss."""
    elf = ELF64.from_path(elf_path)
    offset = elf.vaddr_to_offset(PATCH_SITE_VADDR, 5)
    assert offset == 0x1194
    assert elf.offset_to_vaddr(offset, 5) == PATCH_SITE_VADDR
    assert elf.read_vaddr(PATCH_SITE_VADDR, 5) == bytes.fromhex("e8c7feffff")
    assert elf.read_offset(offset, 2) == bytes.fromhex("e8c7")


def test_preview_edits_are_dry_run(elf_path: Path) -> None:
    """``preview_edits`` changes only the returned bytes, never the source file."""
    original = elf_path.read_bytes()
    elf = ELF64.from_path(elf_path)
    edit = Edit(offset=0x1194, new_bytes=b"\x90" * 5, old_bytes=b"\xe8\xc7\xfe\xff\xff")
    preview = elf.preview_edits([edit])
    assert elf_path.read_bytes() == original
    assert elf.data == original
    assert preview[0x1194:0x1199] == b"\x90" * 5
    assert preview[:0x1194] == original[:0x1194]
    assert preview[0x1199:] == original[0x1199:]


def test_preview_rejects_bad_preimage(elf_path: Path) -> None:
    """A stale original-bytes claim is rejected instead of silently overwritten."""
    elf = ELF64.from_path(elf_path)
    bad = Edit(offset=0x1194, new_bytes=b"\x90" * 5, old_bytes=b"\x00" * 5)
    with pytest.raises(ELFError, match="preimage"):
        elf.preview_edits([bad])


def test_preview_rejects_overlapping_edits(elf_path: Path) -> None:
    """Two edits may not write the same byte."""
    elf = ELF64.from_path(elf_path)
    edits = [
        Edit(offset=0x1194, new_bytes=b"\x90\x90"),
        Edit(offset=0x1195, new_bytes=b"\x90"),
    ]
    with pytest.raises(ELFError, match="overlaps"):
        elf.preview_edits(edits)


def test_preview_rejects_out_of_range_edit(elf_path: Path) -> None:
    """An edit beyond EOF is rejected."""
    elf = ELF64.from_path(elf_path)
    with pytest.raises(ELFError, match="outside"):
        elf.preview_edits([Edit(offset=len(elf.data), new_bytes=b"\x00")])


def test_header_hash_is_stable_across_code_edit(elf_path: Path) -> None:
    """A code/cave edit must not change ELF/header-table bytes."""
    elf = ELF64.from_path(elf_path)
    before = elf.headers_sha256()
    preview = ELF64(elf.preview_edits([Edit(offset=0x1220, new_bytes=b"\x90")]))
    assert preview.headers_sha256() == before


def test_rejects_non_elf_bytes() -> None:
    """Malformed input raises a typed error instead of guessing."""
    with pytest.raises(ELFError):
        ELF64(b"not an elf")


def test_reads_target_symbol_address(elf_path: Path) -> None:
    """The fake PLT target is readable at the expected address."""
    elf = ELF64.from_path(elf_path)
    assert elf.read_vaddr(STRCPY_PLT_VADDR, 2) == b"\xff\x25"


def test_align_up_and_rel32_helpers() -> None:
    """Small address helpers used by the cave finder behave as documented."""
    assert align_up(0x401211, 16) == 0x401220
    assert fits_rel32(0x401199, 0x401220)
    assert not fits_rel32(0x401199, 0x401199 + 2**31)


def test_synthetic_bytes_are_deterministic() -> None:
    """The builder is deterministic so manifests can be compared across runs."""
    assert synthetic_elf_bytes() == synthetic_elf_bytes()
