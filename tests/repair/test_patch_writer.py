"""Tests for the dry-run patch manifest writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.repair.patch_writer import (
    PatchWriterError,
    build_manifest,
    write_manifest,
)
from tests.repair.elf_builder import (
    CAVE_VADDR,
    PATCH_SITE_VADDR,
    RESERVED_END,
    STRCPY_PLT_VADDR,
    write_synthetic_elf,
)


@pytest.fixture()
def elf_path(tmp_path: Path) -> Path:
    """Create a synthetic original ELF."""
    return write_synthetic_elf(tmp_path / "synthetic.elf")


def _manifest(elf_path: Path) -> dict:
    return build_manifest(
        elf_path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        fixture_id="synthetic-01",
        cave_limit_vaddr=RESERVED_END,
    )


def test_manifest_has_required_fields(elf_path: Path) -> None:
    """The manifest records the site, cave, trampoline, invariants and rollback."""
    manifest = _manifest(elf_path)
    assert manifest["schema_version"] == "m5-dryrun-v0"
    assert manifest["dry_run"] is True
    assert manifest["fixture_id"] == "synthetic-01"
    assert manifest["original"]["sha256"]
    assert manifest["patch_site"]["vaddr"] == f"0x{PATCH_SITE_VADDR:x}"
    assert manifest["patch_site"]["original_bytes"] == "e8c7feffff"
    assert manifest["patch_site"]["patch_bytes"] == "e887000000"
    assert manifest["cave"]["vaddr"] == f"0x{CAVE_VADDR:x}"
    assert manifest["cave"]["file_offset"] == "0x1220"
    assert manifest["cave"]["total_size"] == 111
    assert manifest["trampoline"]["message_size"] == 42
    assert len(manifest["trampoline"]["blob"]) == 222
    assert len(manifest["edits"]) == 2
    assert manifest["reversibility"]["matches_original"] is True
    assert manifest["preview"]["candidate_written"] is False
    assert manifest["verdict"] is None
    assert "M3" in manifest["verdict_note"]


def test_manifest_invariants_are_structural_only(elf_path: Path) -> None:
    """Header/entry/segment invariants and byte accounting are recorded."""
    manifest = _manifest(elf_path)
    invariants = manifest["invariants"]
    assert invariants["headers_unchanged"] is True
    assert invariants["entry_unchanged"] is True
    assert invariants["pt_load_count_unchanged"] is True
    assert invariants["pt_load_flags_unchanged"] is True
    assert invariants["no_wx_segments"] is True
    assert invariants["changed_bytes_covered"] is True
    assert 5 <= invariants["changed_byte_count"] <= 5 + 111


def test_write_manifest_writes_json_only(elf_path: Path) -> None:
    """The writer emits JSON and never a candidate ELF."""
    manifest = _manifest(elf_path)
    before = {path.name for path in elf_path.parent.iterdir()}
    out = write_manifest(manifest, elf_path.parent / "manifest.json")
    after = {path.name for path in elf_path.parent.iterdir()}
    assert out.is_file()
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["dry_run"] is True
    assert after - before == {"manifest.json"}
    assert not (elf_path.parent / "candidate.elf").exists()


def test_rejects_unaligned_cave(elf_path: Path) -> None:
    """The cave must be 16-byte aligned."""
    with pytest.raises(PatchWriterError, match="aligned"):
        build_manifest(
            elf_path,
            patch_site_vaddr=PATCH_SITE_VADDR,
            cave_vaddr=CAVE_VADDR + 1,
            strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        )


def test_rejects_nonzero_cave(elf_path: Path) -> None:
    """A non-zero cave byte means the cave is not safe for a dry-run manifest."""
    data = bytearray(elf_path.read_bytes())
    data[0x1220] = 0xCC
    elf_path.write_bytes(bytes(data))
    with pytest.raises(PatchWriterError, match="zero-filled"):
        _manifest(elf_path)


def test_rejects_wrong_site_bytes(elf_path: Path) -> None:
    """A caller-supplied preimage must match the ELF exactly."""
    with pytest.raises(PatchWriterError, match="differ"):
        build_manifest(
            elf_path,
            patch_site_vaddr=PATCH_SITE_VADDR,
            cave_vaddr=CAVE_VADDR,
            strcpy_plt_vaddr=STRCPY_PLT_VADDR,
            expected_site_bytes=b"\x90" * 5,
        )


def test_rejects_site_without_call_opcode(elf_path: Path) -> None:
    """The patch site must start with the expected 5-byte call opcode."""
    data = bytearray(elf_path.read_bytes())
    data[0x1194] = 0x90
    elf_path.write_bytes(bytes(data))
    with pytest.raises(PatchWriterError, match="E8"):
        _manifest(elf_path)


def test_rejects_cave_beyond_limit(elf_path: Path) -> None:
    """The guard must end before the approved reserved range end."""
    with pytest.raises(PatchWriterError, match="beyond"):
        build_manifest(
            elf_path,
            patch_site_vaddr=PATCH_SITE_VADDR,
            cave_vaddr=CAVE_VADDR,
            strcpy_plt_vaddr=STRCPY_PLT_VADDR,
            cave_limit_vaddr=CAVE_VADDR + 10,
        )


def test_rejects_non_executable_target(elf_path: Path) -> None:
    """The original target must be executable."""
    with pytest.raises(PatchWriterError, match="executable"):
        build_manifest(
            elf_path,
            patch_site_vaddr=PATCH_SITE_VADDR,
            cave_vaddr=CAVE_VADDR,
            strcpy_plt_vaddr=0x402000,
        )


def test_refuses_binary_manifest_suffix(elf_path: Path) -> None:
    """The manifest writer cannot be tricked into writing a candidate name."""
    with pytest.raises(PatchWriterError, match="binary suffix"):
        write_manifest(_manifest(elf_path), elf_path.parent / "candidate.elf")
