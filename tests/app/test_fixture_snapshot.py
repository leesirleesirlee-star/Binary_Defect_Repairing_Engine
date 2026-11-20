"""S2 frozen-fixture snapshot and approval binding tests (no pipeline imports)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest

from app.fixture import FIXTURE_ROOT, approve, binding_digest, reset_approval, snapshot

ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_snapshot_is_the_frozen_g1_fixture() -> None:
    data = snapshot()
    assert data["fixture_id"] == "stack-overflow-01"
    assert data["corpus"]["total"] == 9
    assert data["corpus"]["counts"] == {"valid": 5, "invalid": 4, "poc": 0}
    assert [item["id"] for item in data["corpus"]["cases"]] == [
        "valid-0", "valid-1", "valid-5", "valid-31", "valid-punct",
        "invalid-32", "invalid-33", "invalid-64", "invalid-128",
    ]
    assert data["frozen"] is True
    assert data["contract_revision"] == 1


def test_snapshot_hashes_are_the_file_hashes() -> None:
    data = snapshot()
    for name, expected in (
        ("contract.json", data["hashes"]["contract_sha256"]),
        ("cases/cases.json", data["hashes"]["corpus_sha256"]),
    ):
        assert hashlib.sha256((FIXTURE_ROOT / name).read_bytes()).hexdigest() == expected
    assert data["binary"]["sha256"] == _fixture("fixture-manifest.json")["binary"]["sha256"]
    assert data["review_binding_digest"] == binding_digest()


def test_persisted_fixture_documents_validate() -> None:
    jsonschema.validate(_fixture("contract.json"), _schema("ContractV1"))
    jsonschema.validate(_fixture("cases/cases.json"), _schema("CaseSetV1"))
    jsonschema.validate(_fixture("fixture-manifest.json"), _schema("FixtureManifestV1"))


def test_approval_binds_the_three_digests_and_is_idempotent() -> None:
    reset_approval()
    digest = binding_digest()
    approved = approve(digest, reviewer_label="test")
    assert approved["approved"] is True
    assert approved["binding_digest"] == digest
    assert approved["contract_sha256"] == snapshot()["hashes"]["contract_sha256"]
    assert approved["corpus_sha256"] == snapshot()["hashes"]["corpus_sha256"]
    assert approved["binary_sha256"] == snapshot()["binary"]["sha256"]
    assert approve(digest)["approved"] is True


def test_stale_approval_is_rejected() -> None:
    reset_approval()
    with pytest.raises(ValueError, match="stale_approval"):
        approve("0" * 64)


def test_deny_state_is_not_success() -> None:
    reset_approval()
    assert snapshot()["approval"] == {"approved": False, "binding_digest": binding_digest()}
