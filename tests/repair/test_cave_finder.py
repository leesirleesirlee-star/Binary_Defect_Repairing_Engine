"""Tests for the conservative M5 cave finder."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.repair.cave_finder import (
    CaveFinderError,
    build_report,
    find_caves,
    find_caves_in_segments,
)
from pipeline.repair.elf64 import ELF64
from tests.repair.elf_builder import (
    CAVE_VADDR,
    PATCH_SITE_VADDR,
    RESERVED_END,
    RESERVED_START,
    write_synthetic_elf,
)


@pytest.fixture()
def elf(tmp_path: Path) -> ELF64:
    """Create and parse one synthetic ELF64."""
    return ELF64.from_path(write_synthetic_elf(tmp_path / "synthetic.elf"))


def test_finds_aligned_zero_tail(elf: ELF64) -> None:
    """The reserved tail yields an aligned candidate reachable from the call site."""
    candidates = find_caves(
        elf,
        RESERVED_START,
        RESERVED_END,
        min_size=111,
        patch_sites=(PATCH_SITE_VADDR,),
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.vaddr == CAVE_VADDR
    assert candidate.file_offset == 0x1220
    assert candidate.size == RESERVED_END - CAVE_VADDR
    assert candidate.fill == "00"
    assert candidate.alignment == 16
    assert PATCH_SITE_VADDR in candidate.reachable_from


def test_aligned_start_is_rounded_up(elf: ELF64) -> None:
    """A reserved range starting at 0x...211 searches from 0x...220."""
    candidates = find_caves(elf, RESERVED_START, RESERVED_END, min_size=16)
    assert candidates[0].vaddr % 16 == 0
    assert candidates[0].vaddr == CAVE_VADDR


def test_rejects_range_outside_executable_segment(elf: ELF64) -> None:
    """The cave must live in an executable load segment."""
    with pytest.raises(CaveFinderError, match="executable"):
        find_caves(elf, 0x402000, 0x402100, min_size=16)


def test_rejects_bad_range(elf: ELF64) -> None:
    """An empty or reversed range is an input error."""
    with pytest.raises(CaveFinderError):
        find_caves(elf, RESERVED_END, RESERVED_START, min_size=16)


def test_skips_nonzero_cave(tmp_path: Path) -> None:
    """A reserved range with a non-zero byte does not yield the full candidate."""
    path = write_synthetic_elf(tmp_path / "nonzero.elf")
    data = bytearray(path.read_bytes())
    data[0x1220] = 0xCC
    path.write_bytes(bytes(data))
    elf = ELF64.from_path(path)
    candidates = find_caves(elf, RESERVED_START, RESERVED_END, min_size=0xDE0)
    assert candidates == []


def test_skips_short_zero_run(tmp_path: Path) -> None:
    """A zero run shorter than ``min_size`` is not returned."""
    path = write_synthetic_elf(tmp_path / "short.elf")
    data = bytearray(path.read_bytes())
    # Split the tail so the first zero run is only 16 bytes.
    data[0x1230] = 0xCC
    path.write_bytes(bytes(data))
    elf = ELF64.from_path(path)
    candidates = find_caves(elf, RESERVED_START, RESERVED_END, min_size=0xDE0)
    assert candidates == []


def test_does_not_scan_code_section(elf: ELF64) -> None:
    """The candidate search starts after ``.text`` and is not a .text scan."""
    candidates = find_caves(elf, 0x401000, 0x401211, min_size=16)
    assert all(candidate.vaddr >= RESERVED_START for candidate in candidates)


def test_report_is_json_friendly(tmp_path: Path) -> None:
    """The CLI-facing report carries the ELF hash and string addresses."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = build_report(path, RESERVED_START, RESERVED_END, 111, [PATCH_SITE_VADDR])
    assert report["status"] == "ok"
    assert report["elf_sha256"]
    assert report["candidates"][0]["vaddr"] == f"0x{CAVE_VADDR:x}"
    assert report["candidates"][0]["reachable_from"] == [f"0x{PATCH_SITE_VADDR:x}"]


def test_report_no_candidate(tmp_path: Path) -> None:
    """A valid range with no large enough cave returns ``no_candidate``."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = build_report(path, RESERVED_START, RESERVED_END, 0x2000)
    assert report["status"] == "no_candidate"
    assert report["candidates"] == []


def test_scans_all_executable_segments(elf: ELF64) -> None:
    """The product-facing scan does not assume a fixture-reserved range."""
    candidates = find_caves_in_segments(
        elf,
        min_size=111,
        patch_sites=(PATCH_SITE_VADDR,),
    )
    assert any(candidate.vaddr == CAVE_VADDR for candidate in candidates)
    assert all(candidate.scope == "executable_segments" for candidate in candidates)


def test_general_report_mode(tmp_path: Path) -> None:
    """Omitting both bounds reports an all-executable-segments scan."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = build_report(path, None, None, 111, [PATCH_SITE_VADDR])
    assert report["status"] == "ok"
    assert report["range"] == {"mode": "all_executable_segments"}
    assert report["candidates"][0]["scope"] == "executable_segments"


def test_one_bound_is_an_error(tmp_path: Path) -> None:
    """A half-specified range is rejected rather than guessed."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = build_report(path, RESERVED_START, None, 111)
    assert report["status"] == "error"
    assert "together" in report["error"]
