"""Malformed-ELF robustness tests for the M5 parser and preflight.

Every input is a synthetic byte mutation.  The tests assert that the tools fail
closed: `ELFError`/`error`/`unsupported`/`no_candidate`, no crash, no manifest
and no candidate.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from pipeline.repair.cave_finder import build_report
from pipeline.repair.elf64 import ELF64, ELFError
from pipeline.repair.validate_fixture import validate_fixture
from tests.repair.elf_builder import (
    PATCH_SITE_VADDR,
    PHDR_OFFSET,
    RESERVED_END,
    RESERVED_START,
    STRCPY_PLT_VADDR,
    synthetic_elf_bytes,
)

RX_PHDR = PHDR_OFFSET
RX_P_FLAGS = RX_PHDR + 4
RX_P_OFFSET = RX_PHDR + 8
RX_P_FILESZ = RX_PHDR + 32
RX_P_MEMSZ = RX_PHDR + 40
SECOND_PHDR = PHDR_OFFSET + 56
SECOND_P_VADDR = SECOND_PHDR + 16
SECOND_P_OFFSET = SECOND_PHDR + 8
SECOND_P_FILESZ = SECOND_PHDR + 32
SECOND_P_MEMSZ = SECOND_PHDR + 40


def _write_variant(tmp_path: Path, mutate) -> Path:
    """Apply one byte mutation to the synthetic image and write it."""
    data = bytearray(synthetic_elf_bytes())
    mutate(data)
    path = tmp_path / "malformed.elf"
    path.write_bytes(bytes(data))
    return path


def _assert_fails_closed(path: Path, tmp_path: Path) -> None:
    """Assert parser/CLI/preflight all fail without producing a manifest."""
    with pytest.raises(ELFError):
        ELF64.from_path(path)
    report = build_report(path, RESERVED_START, RESERVED_END, 111)
    assert report["status"] == "error"
    manifest_path = tmp_path / "must-not-exist.json"
    preflight = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
        manifest_out=manifest_path,
    )
    assert preflight["status"] == "error"
    assert not manifest_path.exists()
    assert not (tmp_path / "candidate.elf").exists()


def test_truncated_elf_header(tmp_path: Path) -> None:
    """A file shorter than the ELF64 header is rejected."""
    path = tmp_path / "truncated-header.elf"
    path.write_bytes(synthetic_elf_bytes()[:32])
    _assert_fails_closed(path, tmp_path)


def test_truncated_program_header_table(tmp_path: Path) -> None:
    """A program-header table truncated by one byte is rejected."""
    path = tmp_path / "truncated-phdr.elf"
    path.write_bytes(synthetic_elf_bytes()[: PHDR_OFFSET + 3 * 56 - 1])
    _assert_fails_closed(path, tmp_path)


def test_truncated_section_header_table(tmp_path: Path) -> None:
    """A section-header table truncated by one byte is rejected."""
    path = tmp_path / "truncated-shdr.elf"
    path.write_bytes(synthetic_elf_bytes()[: 0x3100 + 4 * 64 - 1])
    _assert_fails_closed(path, tmp_path)


def test_wrong_machine(tmp_path: Path) -> None:
    """An i386 e_machine is rejected by the ELF64 x86-64 parser."""

    def mutate(data: bytearray) -> None:
        struct.pack_into("<H", data, 18, 3)

    _assert_fails_closed(_write_variant(tmp_path, mutate), tmp_path)


def test_huge_phnum(tmp_path: Path) -> None:
    """An e_phnum that runs past EOF is rejected without looping over it."""

    def mutate(data: bytearray) -> None:
        struct.pack_into("<H", data, 56, 0xFFFF)

    _assert_fails_closed(_write_variant(tmp_path, mutate), tmp_path)


def test_huge_shnum(tmp_path: Path) -> None:
    """An e_shnum that runs past EOF is rejected without looping over it."""

    def mutate(data: bytearray) -> None:
        struct.pack_into("<H", data, 60, 0xFFFF)

    _assert_fails_closed(_write_variant(tmp_path, mutate), tmp_path)


def test_segment_file_range_past_eof(tmp_path: Path) -> None:
    """A PT_LOAD whose file range exceeds the file is rejected."""
    def mutate(data: bytearray) -> None:
        struct.pack_into("<Q", data, RX_P_FILESZ, 0x2000)

    _assert_fails_closed(_write_variant(tmp_path, mutate), tmp_path)


def test_segment_vaddr_offset_misaligned(tmp_path: Path) -> None:
    """A PT_LOAD whose vaddr/offset congruence breaks p_align is rejected."""
    def mutate(data: bytearray) -> None:
        struct.pack_into("<Q", data, RX_P_OFFSET, 0x2100)

    _assert_fails_closed(_write_variant(tmp_path, mutate), tmp_path)


def test_zero_length_rx_segment_is_unsupported(tmp_path: Path) -> None:
    """A zero-length R-X segment is structurally unusable, not a cave."""
    def mutate(data: bytearray) -> None:
        struct.pack_into("<Q", data, RX_P_FILESZ, 0)
        struct.pack_into("<Q", data, RX_P_MEMSZ, 0)

    path = _write_variant(tmp_path, mutate)
    elf = ELF64.from_path(path)
    assert elf.executable_load_segments()[0].p_filesz == 0
    report = build_report(path, RESERVED_START, RESERVED_END, 111)
    assert report["status"] == "error"
    preflight = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert preflight["status"] == "unsupported"


def test_invalid_segment_permissions(tmp_path: Path) -> None:
    """A non-executable R-X segment is unsupported, not silently used."""
    def mutate(data: bytearray) -> None:
        struct.pack_into("<I", data, RX_P_FLAGS, 0)

    path = _write_variant(tmp_path, mutate)
    report = build_report(path, RESERVED_START, RESERVED_END, 111)
    assert report["status"] == "error"
    preflight = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert preflight["status"] == "unsupported"


def test_overlapping_ptload_yields_no_candidate(tmp_path: Path) -> None:
    """An overlapping second PT_LOAD invalidates the candidate, not the parser."""
    def mutate(data: bytearray) -> None:
        struct.pack_into("<Q", data, SECOND_P_VADDR, 0x401200)
        struct.pack_into("<Q", data, SECOND_P_OFFSET, 0x1200)
        struct.pack_into("<Q", data, SECOND_P_FILESZ, 0x100)
        struct.pack_into("<Q", data, SECOND_P_MEMSZ, 0x100)

    path = _write_variant(tmp_path, mutate)
    report = build_report(path, RESERVED_START, RESERVED_END, 111)
    assert report["status"] == "no_candidate"
    preflight = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert preflight["status"] == "no_candidate"
    assert preflight["max_zero_run"] >= 0
    assert not (tmp_path / "candidate.elf").exists()
