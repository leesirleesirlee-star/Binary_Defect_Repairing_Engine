"""EditManifestV1 alignment tests (standard library only)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pipeline.repair.manifest_schema import (
    EDIT_MANIFEST_V1_VERSION,
    PROVISIONAL_SCHEMA,
    V1_REQUIRED_TOP_LEVEL,
    ManifestShapeError,
    to_edit_manifest_v1,
    validate_edit_manifest_v1,
)
from pipeline.repair import patch_writer
from pipeline.repair.patch_writer import build_manifest, build_manifest_v1
from tests.repair.elf_builder import (
    CAVE_VADDR,
    PATCH_SITE_VADDR,
    RESERVED_END,
    STRCPY_PLT_VADDR,
    write_synthetic_elf,
)


def _manifest(path: Path):
    return build_manifest(
        path,
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        cave_limit_vaddr=RESERVED_END,
        fixture_id="synthetic-tail",
        plan_id="plan-draft-1",
    )


def test_v1_mapping_uses_official_names(tmp_path: Path) -> None:
    """The opt-in mapping uses integer v1 and official top-level names."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    provisional = _manifest(path)
    mapped = to_edit_manifest_v1(provisional)

    validate_edit_manifest_v1(mapped)
    assert mapped["schema_version"] == EDIT_MANIFEST_V1_VERSION == 1
    assert mapped["manifest_kind"] == "EditManifestV1"
    assert "schema_kind" not in mapped
    assert "schema_status" not in mapped
    assert "schema_mapping" not in mapped
    assert mapped["fixture_id"] == "synthetic-tail"
    assert mapped["plan_id"] == "plan-draft-1"
    assert mapped["extensions"]["provisional"] is True
    assert mapped["extensions"]["schema_mapping"]["target"] == "EditManifestV1"
    assert mapped["preview"]["candidate_written"] is False
    assert mapped["verdict"] is None

    # Provenance is retained, but under extensions rather than at top level.
    assert provisional["schema_version"] == PROVISIONAL_SCHEMA
    assert provisional["schema_mapping"]["source"] == PROVISIONAL_SCHEMA


def test_build_manifest_v1_is_the_opt_in_switch(tmp_path: Path) -> None:
    """build_manifest stays provisional; build_manifest_v1 returns the mapping."""
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    kwargs = dict(
        patch_site_vaddr=PATCH_SITE_VADDR,
        cave_vaddr=CAVE_VADDR,
        strcpy_plt_vaddr=STRCPY_PLT_VADDR,
        cave_limit_vaddr=RESERVED_END,
        fixture_id="synthetic-tail",
        plan_id="plan-draft-1",
    )
    assert build_manifest(path, **kwargs)["schema_version"] == PROVISIONAL_SCHEMA
    mapped = build_manifest_v1(path, **kwargs)
    assert mapped["schema_version"] == 1
    assert mapped["manifest_kind"] == "EditManifestV1"


def test_official_schema_contract_matches_mapping(tmp_path: Path) -> None:
    """The checked-in EditManifestV1 schema and the mapper agree on the contract."""
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "EditManifestV1.schema.json"
    )
    assert schema_path.exists(), "official EditManifestV1 schema is missing"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema["properties"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(V1_REQUIRED_TOP_LEVEL)
    assert properties["schema_version"]["const"] == EDIT_MANIFEST_V1_VERSION
    assert properties["dry_run"]["const"] is True
    assert properties["preview"]["properties"]["candidate_written"]["const"] is False
    assert properties["verdict"]["type"] == "null"

    mapped = to_edit_manifest_v1(
        _manifest(write_synthetic_elf(tmp_path / "synthetic.elf"))
    )
    assert set(mapped) <= set(properties)
    assert set(schema["required"]) <= set(mapped)
    validate_edit_manifest_v1(mapped)


def test_v1_rejects_extra_top_level_field(tmp_path: Path) -> None:
    """schema_kind/schema_status are not official v1 fields."""
    mapped = to_edit_manifest_v1(_manifest(write_synthetic_elf(tmp_path / "synthetic.elf")))
    bad = copy.deepcopy(mapped)
    bad["schema_kind"] = "EditManifestV1"
    with pytest.raises(ManifestShapeError, match="unexpected top-level"):
        validate_edit_manifest_v1(bad)


def test_v1_rejects_string_schema_version(tmp_path: Path) -> None:
    """The version must be integer 1, not the provisional string."""
    mapped = to_edit_manifest_v1(_manifest(write_synthetic_elf(tmp_path / "synthetic.elf")))
    bad = copy.deepcopy(mapped)
    bad["schema_version"] = PROVISIONAL_SCHEMA
    with pytest.raises(ManifestShapeError, match="schema_version"):
        validate_edit_manifest_v1(bad)


def test_v1_requires_fixture_and_plan_ids(tmp_path: Path) -> None:
    """fixture_id and plan_id are required in v1."""
    mapped = to_edit_manifest_v1(_manifest(write_synthetic_elf(tmp_path / "synthetic.elf")))
    for field in ("fixture_id", "plan_id"):
        bad = copy.deepcopy(mapped)
        del bad[field]
        with pytest.raises(ManifestShapeError, match=field):
            validate_edit_manifest_v1(bad)


def test_v1_rejects_candidate_or_verdict(tmp_path: Path) -> None:
    """A v1 manifest cannot claim a candidate or a verdict."""
    mapped = to_edit_manifest_v1(_manifest(write_synthetic_elf(tmp_path / "synthetic.elf")))
    bad_candidate = copy.deepcopy(mapped)
    bad_candidate["preview"]["candidate_written"] = True
    with pytest.raises(ManifestShapeError, match="candidate_written"):
        validate_edit_manifest_v1(bad_candidate)

    bad_verdict = copy.deepcopy(mapped)
    bad_verdict["verdict"] = "verified_against_stated_criteria"
    with pytest.raises(ManifestShapeError, match="verdict"):
        validate_edit_manifest_v1(bad_verdict)


def test_cli_v1_writes_schema_valid_manifest(tmp_path: Path) -> None:
    path = write_synthetic_elf(tmp_path / "synthetic.elf")
    out = tmp_path / "edit-manifest.json"
    rc = patch_writer.main([
        "--elf", str(path),
        "--patch-site", hex(PATCH_SITE_VADDR),
        "--cave", hex(CAVE_VADDR),
        "--strcpy-plt", hex(STRCPY_PLT_VADDR),
        "--cave-limit", hex(RESERVED_END),
        "--fixture-id", "synthetic-tail",
        "--plan-id", "plan-cli-1",
        "--manifest-version", "v1",
        "--out", str(out),
    ])
    assert rc == 0
    manifest = json.loads(out.read_text())
    assert manifest["schema_version"] == 1
    assert manifest["manifest_kind"] == "EditManifestV1"
    validate_edit_manifest_v1(manifest)
