"""Tests for the read-only persisted-JSON loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.loader import (
    ArtifactInvalid,
    ArtifactMissing,
    ArtifactUnsafe,
    load,
)


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_load_returns_the_persisted_object_verbatim(tmp_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "verdict": {"outcome": "not_run"},
        "unsupported": "unsupported",
        "nested": {"values": [1, 2, 3]},
    }
    _write(tmp_path, "artifact.json", payload)
    assert load("artifact.json", root=tmp_path) == payload


def test_load_accepts_an_absolute_path_inside_the_root(tmp_path: Path) -> None:
    payload = {"status": "not_run"}
    target = _write(tmp_path, "artifact.json", payload)
    assert load(target, root=tmp_path) == payload


def test_missing_artifact_is_a_distinct_error(tmp_path: Path) -> None:
    with pytest.raises(ArtifactMissing):
        load("missing.json", root=tmp_path)


@pytest.mark.parametrize("bad_path", ["../outside.json", "../../outside.json", "/etc/hosts"])
def test_paths_outside_the_root_are_rejected(tmp_path: Path, bad_path: str) -> None:
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactUnsafe):
        load(bad_path, root=tmp_path)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(outside)
    with pytest.raises(ArtifactUnsafe):
        load("link.json", root=tmp_path)


def test_non_json_extension_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "artifact.txt"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactUnsafe):
        load("artifact.txt", root=tmp_path)


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(ArtifactInvalid):
        load("broken.json", root=tmp_path)


def test_top_level_must_be_object(tmp_path: Path) -> None:
    _write(tmp_path, "array.json", [1, 2, 3])
    with pytest.raises(ArtifactInvalid):
        load("array.json", root=tmp_path)


def test_empty_and_nul_paths_are_rejected(tmp_path: Path) -> None:
    for bad_path in ("", "   ", "artifact\x00.json"):
        with pytest.raises(ArtifactUnsafe):
            load(bad_path, root=tmp_path)
