"""Golden manifest regression tests.

These tests compare deterministic output against a checked-in snapshot.  A
failure must be investigated; the test never rewrites the snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.repair.patch_writer import build_manifest
from pipeline.repair.validate_fixture import validate_fixture
from tests.repair.elf_builder import (
    CAVE_VADDR,
    PATCH_SITE_VADDR,
    RESERVED_END,
    RESERVED_START,
    STRCPY_PLT_VADDR,
    write_synthetic_elf,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "manifest-cases.json"


def _golden() -> dict:
    """Load the checked-in snapshot without modifying it."""
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _case(case_id: str) -> dict:
    """Return one named golden case."""
    for case in _golden()["cases"]:
        if case["id"] == case_id:
            return case
    raise AssertionError(f"missing golden case {case_id}")


def test_with_tail_matches_golden(tmp_path: Path) -> None:
    """The generated manifest matches every selected golden field exactly."""
    case = _case("with-reserved-tail")
    expected = case["expected"]
    path = write_synthetic_elf(tmp_path / "with-tail.elf")
    manifest = build_manifest(
        path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        fixture_id="synthetic-tail",
        cave_limit_vaddr=RESERVED_END,
    )

    assert manifest["manifest_sha256"] == expected["manifest_sha256"]
    assert manifest["original"]["sha256"] == expected["original_sha256"]
    assert manifest["patch_site"]["vaddr"] == expected["patch_site"]["vaddr"]
    assert manifest["patch_site"]["file_offset"] == expected["patch_site"]["file_offset"]
    assert manifest["patch_site"]["original_bytes"] == expected["patch_site"]["original_bytes"]
    assert manifest["patch_site"]["patch_bytes"] == expected["patch_site"]["patch_bytes"]
    assert manifest["patch_site"]["call_rel32"] == expected["patch_site"]["call_rel32"]
    assert manifest["cave"]["vaddr"] == expected["cave"]["vaddr"]
    assert manifest["cave"]["file_offset"] == expected["cave"]["file_offset"]
    assert manifest["cave"]["total_size"] == expected["cave"]["total_size"]
    assert manifest["cave"]["code_size"] == expected["cave"]["code_size"]
    assert manifest["cave"]["message_size"] == expected["cave"]["message_size"]
    assert manifest["trampoline"]["blob_sha256"] == expected["trampoline_blob_sha256"]
    assert manifest["preview"]["candidate_sha256_if_applied"] == expected["preview_sha256"]
    for key, value in expected["invariants"].items():
        assert manifest["invariants"][key] == value, key
    assert manifest["reversibility"]["matches_original"] is True
    assert (
        manifest["reversibility"]["restored_sha256"]
        == expected["reversibility"]["restored_sha256"]
    )
    assert manifest["verdict"] is None
    assert not (tmp_path / "candidate.elf").exists()


def test_without_tail_matches_golden_refusal(tmp_path: Path) -> None:
    """The no-tail fixture deterministically returns unsupported, not a manifest."""
    case = _case("without-reserved-tail")
    expected = case["expected"]
    path = write_synthetic_elf(tmp_path / "no-tail.elf", reserved_tail=False)
    manifest_path = tmp_path / "must-not-exist.json"
    report = validate_fixture(
        path,
        start=RESERVED_START,
        end=RESERVED_END,
        patch_site=PATCH_SITE_VADDR,
        strcpy_plt=STRCPY_PLT_VADDR,
        manifest_out=manifest_path,
    )

    assert report["status"] == expected["status"]
    assert report["original_sha256"] == expected["original_sha256"]
    assert report.get("manifest_sha256") is None
    assert report["candidate_written"] is False
    assert report["verdict_written_by_m5"] is False
    assert not manifest_path.exists()
    cave_stage = next(stage for stage in report["stages"] if stage["name"] == "cave_finder")
    assert expected["cave_finder_detail_contains"] in cave_stage["detail"]


def test_golden_file_is_not_rewritten(tmp_path: Path) -> None:
    """Running the tests does not modify the checked-in snapshot."""
    before = GOLDEN_PATH.read_bytes()
    test_with_tail_matches_golden(tmp_path)
    assert GOLDEN_PATH.read_bytes() == before
