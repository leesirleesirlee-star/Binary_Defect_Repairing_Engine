"""Tests for the M5 structural self-check (not a verdict)."""

from __future__ import annotations

import copy
from pathlib import Path

from pipeline.repair.patch_writer import build_manifest
from pipeline.repair.self_check import check_manifest
from tests.repair.elf_builder import (
    CAVE_VADDR,
    PATCH_SITE_VADDR,
    RESERVED_END,
    STRCPY_PLT_VADDR,
    write_synthetic_elf,
)


def _fixture(tmp_path: Path) -> tuple[Path, dict]:
    """Create a synthetic ELF and a valid dry-run manifest."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    manifest = build_manifest(
        path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        fixture_id="synthetic-01",
        cave_limit_vaddr=RESERVED_END,
    )
    return path, manifest


def test_valid_manifest_passes(tmp_path: Path) -> None:
    """A structurally valid manifest passes every structural check."""
    path, manifest = _fixture(tmp_path)
    report = check_manifest(path, manifest)
    assert report["status"] == "checks_passed"
    assert report["failures"] == []
    assert report["verdict_written_by_m5"] is False
    assert any(check["name"] == "reversibility" and check["passed"] for check in report["checks"])


def test_detects_tampered_patch_bytes(tmp_path: Path) -> None:
    """Changing a patch byte without updating the preview hash is caught."""
    path, manifest = _fixture(tmp_path)
    tampered = copy.deepcopy(manifest)
    tampered["edits"][0]["patch_bytes"] = "90" * 5
    report = check_manifest(path, tampered)
    assert report["status"] == "checks_failed"
    assert "preview_hash_matches_manifest" in report["failures"]


def test_detects_tampered_offset(tmp_path: Path) -> None:
    """Moving an edit onto the ELF header is caught by the preimage check."""
    path, manifest = _fixture(tmp_path)
    tampered = copy.deepcopy(manifest)
    tampered["edits"][0]["file_offset"] = "0x0"
    report = check_manifest(path, tampered)
    assert report["status"] == "checks_failed"


def test_detects_changed_original(tmp_path: Path) -> None:
    """A changed original fails the original-hash check."""
    path, manifest = _fixture(tmp_path)
    data = bytearray(path.read_bytes())
    data[0x1220] = 0xCC
    path.write_bytes(bytes(data))
    report = check_manifest(path, manifest)
    assert report["status"] == "checks_failed"
    assert any(failure.startswith("original_sha256_matches") for failure in report["failures"])


def test_detects_candidate_written_claim(tmp_path: Path) -> None:
    """M5 must not claim that a candidate file was written."""
    path, manifest = _fixture(tmp_path)
    tampered = copy.deepcopy(manifest)
    tampered["preview"]["candidate_written"] = True
    report = check_manifest(path, tampered)
    assert report["status"] == "checks_failed"
    assert any(
        failure.startswith("no_candidate_written_by_manifest")
        for failure in report["failures"]
    )


def test_detects_non_dry_run_manifest(tmp_path: Path) -> None:
    """A manifest that is not explicitly dry-run is rejected."""
    path, manifest = _fixture(tmp_path)
    tampered = copy.deepcopy(manifest)
    tampered["dry_run"] = False
    report = check_manifest(path, tampered)
    assert report["status"] == "checks_failed"
    assert any(failure.startswith("dry_run_flag") for failure in report["failures"])


def test_self_check_writes_no_files(tmp_path: Path) -> None:
    """The checker only reads; it must not create a candidate or verdict."""
    path, manifest = _fixture(tmp_path)
    before = {item.name for item in tmp_path.iterdir()}
    check_manifest(path, manifest)
    after = {item.name for item in tmp_path.iterdir()}
    assert after == before
