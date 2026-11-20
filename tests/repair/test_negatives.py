"""Negative-path, determinism, reversibility and schema-mapping tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.repair.cave_finder import CaveFinderError, find_caves
from pipeline.repair.elf64 import ELF64, ELFError, encode_rel32_branch
from pipeline.repair.manifest_schema import (
    EXTENSION_SLOTS,
    ManifestShapeError,
    normalize_provisional,
    to_edit_manifest_v1,
    validate_provisional_shape,
)
from pipeline.repair.patch_writer import (
    PatchWriterError,
    build_manifest,
    write_manifest,
)
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


def _manifest(path: Path, patch_site: int = PATCH_SITE_VADDR) -> dict:
    return build_manifest(
        path,
        patch_site_vaddr=patch_site,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        fixture_id="synthetic-01",
        cave_limit_vaddr=RESERVED_END,
    )


def test_patch_site_not_executable(tmp_path: Path) -> None:
    """A patch site in an R-- segment is rejected."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    with pytest.raises(PatchWriterError, match="executable"):
        build_manifest(
            path,
            patch_site_vaddr=0x402000,
            cave_vaddr=CAVE_VADDR,
            strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        )


def test_patch_site_outside_load(tmp_path: Path) -> None:
    """A patch site outside every file-backed load segment is rejected."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    with pytest.raises(PatchWriterError, match="not file-backed"):
        build_manifest(
            path,
            patch_site_vaddr=0x500000,
            cave_vaddr=CAVE_VADDR,
            strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        )


def test_guard_overruns_segment(tmp_path: Path) -> None:
    """A guard that does not fit before the segment end is rejected."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    with pytest.raises(PatchWriterError, match="does not fit"):
        build_manifest(
            path,
            patch_site_vaddr=PATCH_SITE_VADDR,
            cave_vaddr=0x401FC0,
            strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        )


def test_rel32_branch_out_of_range() -> None:
    """The low-level encoder refuses a target beyond signed 32-bit reach."""
    with pytest.raises(ELFError, match="cannot reach"):
        encode_rel32_branch(0xE8, 0x401194, 0x401194 + 2**31 + 5)


def test_cave_range_past_segment(tmp_path: Path) -> None:
    """A cave range that crosses the segment boundary is rejected."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    elf = ELF64.from_path(path)
    with pytest.raises(CaveFinderError):
        find_caves(elf, RESERVED_START, 0x402800, min_size=16)


def test_no_reserved_tail_is_unsupported(tmp_path: Path) -> None:
    """The pre-ADR fixture without a file-backed tail is not silently adapted."""
    path = write_synthetic_elf(tmp_path / "no-tail.elf", reserved_tail=False)
    elf = ELF64.from_path(path)
    with pytest.raises(CaveFinderError, match="not in one PT_LOAD"):
        find_caves(elf, RESERVED_START, RESERVED_END, min_size=16)
    with pytest.raises(PatchWriterError, match="not file-backed"):
        _manifest(path)


def test_validate_fixture_passes_on_synthetic(tmp_path: Path) -> None:
    """The preflight framework passes on a structurally complete synthetic ELF."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert report["status"] == "dry_run_checks_passed"
    assert report["candidate_written"] is False
    assert report["verdict_written_by_m5"] is False
    assert not (tmp_path / "candidate.elf").exists()


def test_validate_fixture_reports_unsupported_without_tail(tmp_path: Path) -> None:
    """A missing reserved tail returns unsupported, not a guessed manifest."""
    path = write_synthetic_elf(tmp_path / "no-tail.elf", reserved_tail=False)
    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert report["status"] == "unsupported"
    assert report["candidate_written"] is False


def test_validate_fixture_reports_no_candidate_with_max_run(tmp_path: Path) -> None:
    """A cave below the requested size returns no_candidate and the max run."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
        min_size=0x2000,
    )
    assert report["status"] == "no_candidate"
    assert report["max_zero_run"] == RESERVED_END - RESERVED_START


def test_validate_fixture_reports_patch_preimage_error(tmp_path: Path) -> None:
    """A wrong patch-site opcode is an error and includes the measured bytes."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    data = bytearray(path.read_bytes())
    data[0x1194] = 0x90
    path.write_bytes(bytes(data))
    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert report["status"] == "error"
    assert report["patch_site_original_bytes"].startswith("90")


def test_validate_fixture_rejects_non_executable_patch_site(tmp_path: Path) -> None:
    """A patch site in an R-- segment is unsupported, not silently moved."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=0x402000,
        strcpy_plt=STRCPY_PLT_VADDR,
    )
    assert report["status"] == "unsupported"


def test_manifest_is_deterministic(tmp_path: Path) -> None:
    """Same input produces identical JSON bytes and the same manifest hash."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    first = _manifest(path)
    second = _manifest(path)
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    out_a = write_manifest(first, tmp_path / "manifest-a.json")
    out_b = write_manifest(second, tmp_path / "manifest-b.json")
    assert out_a.read_bytes() == out_b.read_bytes()


def test_manifest_hash_is_path_independent(tmp_path: Path) -> None:
    """Local paths are evidence metadata and must not change the canonical hash."""
    first_path = write_synthetic_elf(tmp_path / "first.elf")
    second_path = write_synthetic_elf(tmp_path / "second.elf")
    first = _manifest(first_path)
    second = _manifest(second_path)
    assert first["original"]["path"] != second["original"]["path"]
    assert first["manifest_sha256"] == second["manifest_sha256"]


def test_manifest_hash_ignores_created_at(tmp_path: Path) -> None:
    """Evidence timestamps do not change the canonical manifest hash."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    first = build_manifest(
        path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        cave_limit_vaddr=RESERVED_END,
        created_at="2026-11-20T10:00:00Z",
    )
    second = build_manifest(
        path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        cave_limit_vaddr=RESERVED_END,
        created_at="2026-11-21T10:00:00Z",
    )
    assert first["created_at"] != second["created_at"]
    assert first["manifest_sha256"] == second["manifest_sha256"]


def test_reversibility_across_patch_sites(tmp_path: Path) -> None:
    """Manifest rollback restores the original hash for start/middle/end sites."""
    for index, site in enumerate((0x401010, 0x401194, 0x40120C)):
        path = write_synthetic_elf(tmp_path / f"site-{index}.elf", patch_site_vaddr=site)
        manifest = _manifest(path, patch_site=site)
        assert manifest["reversibility"]["matches_original"] is True
        assert manifest["reversibility"]["restored_sha256"] == manifest["original"]["sha256"]
        report = check_manifest(path, manifest)
        assert report["status"] == "checks_passed"


def test_schema_mapping_preserves_required_fields(tmp_path: Path) -> None:
    """The provisional manifest has stable slots for the future v1 mapping."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    manifest = _manifest(path)
    validate_provisional_shape(manifest)
    normalized = normalize_provisional(manifest)
    assert set(EXTENSION_SLOTS).issubset(normalized["extensions"])
    assert normalized["schema_mapping"]["target"] == "EditManifestV1"
    mapped = to_edit_manifest_v1(manifest)
    assert mapped["schema_version"] == 1
    assert mapped["manifest_kind"] == "EditManifestV1"
    assert "schema_status" not in mapped
    assert mapped["extensions"]["schema_mapping"]["status"] == "draft-pending-M1"
    assert mapped["fixture_id"]
    assert mapped["plan_id"]
    assert mapped["verdict"] is None


def test_schema_rejects_non_null_verdict(tmp_path: Path) -> None:
    """An M5 manifest cannot smuggle a verdict into the shape."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    manifest = _manifest(path)
    manifest["verdict"] = "verified_against_stated_criteria"
    with pytest.raises(ManifestShapeError, match="verdict=null"):
        validate_provisional_shape(manifest)


def test_self_check_detects_manifest_hash_tamper(tmp_path: Path) -> None:
    """Changing a manifest field without refreshing its hash is caught."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    manifest = _manifest(path)
    manifest["fixture_id"] = "tampered"
    report = check_manifest(path, manifest)
    assert report["status"] == "checks_failed"
    assert any(
        failure.startswith("manifest_sha256_matches") for failure in report["failures"]
    )
