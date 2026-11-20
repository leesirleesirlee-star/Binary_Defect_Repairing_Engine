"""Extreme boundary tests for the M5 dry-run tools."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from pipeline.repair.cave_finder import find_caves
from pipeline.repair.elf64 import ELF64, ELFError, encode_rel32_branch
from pipeline.repair.patch_writer import build_manifest
from pipeline.repair.self_check import check_manifest
from pipeline.repair.validate_fixture import validate_fixture
from tests.repair.elf_builder import (
    CAVE_VADDR,
    PATCH_SITE_VADDR,
    RESERVED_END,
    RESERVED_START,
    STRCPY_PLT_VADDR,
    write_synthetic_elf,
)


def test_cave_exactly_guard_size(tmp_path: Path) -> None:
    """A cave of exactly 111 bytes is accepted; 110 is not."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    elf = ELF64.from_path(path)
    exactly = find_caves(
        elf,
        CAVE_VADDR,
        CAVE_VADDR + 111,
        min_size=111,
    )
    assert len(exactly) == 1
    assert exactly[0].size == 111

    too_small = find_caves(
        elf,
        CAVE_VADDR,
        CAVE_VADDR + 110,
        min_size=111,
    )
    assert too_small == []

    manifest = build_manifest(
        path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        cave_limit_vaddr=CAVE_VADDR + 111,
    )
    assert manifest["cave"]["total_size"] == 111
    assert check_manifest(path, manifest)["status"] == "checks_passed"


def test_rel32_exact_positive_limit() -> None:
    """A displacement of exactly INT32_MAX is accepted; one more is rejected."""
    source = 0x1000
    target = source + 5 + (2**31 - 1)
    encoded = encode_rel32_branch(0xE8, source, target)
    assert encoded[0] == 0xE8
    assert struct.unpack_from("<i", encoded, 1)[0] == 2**31 - 1

    with pytest.raises(ELFError, match="cannot reach"):
        encode_rel32_branch(0xE8, source, target + 1)


def test_patch_site_last_five_bytes_of_rx(tmp_path: Path) -> None:
    """The last 5 bytes of the R-X segment can be the redirect site."""
    site = RESERVED_END - 5
    path = write_synthetic_elf(tmp_path / "synthetic.elf", patch_site_vaddr=site)
    manifest = build_manifest(
        path,
        patch_site_vaddr=site,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        cave_limit_vaddr=RESERVED_END,
    )
    assert manifest["patch_site"]["vaddr"] == "0x401ffb"
    assert manifest["patch_site"]["file_offset"] == "0x1ffb"
    assert manifest["reversibility"]["matches_original"] is True
    assert check_manifest(path, manifest)["status"] == "checks_passed"

    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=site,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert report["status"] == "dry_run_checks_passed"
