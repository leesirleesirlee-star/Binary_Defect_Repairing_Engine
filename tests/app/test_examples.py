"""Validate app/examples JSON against the frozen schemas when they exist.

At G0 the contract schemas are not on `main`; the test reports that as a
deliberate `not_run` instead of inventing a shape.  When M1 lands the schemas,
every example under app/examples/ is validated by filename to its schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "app" / "examples"
SCHEMAS = ROOT / "schemas"


def _schema_files() -> list[Path]:
    return sorted(SCHEMAS.glob("*.schema.json"))


def test_examples_validate_against_frozen_schemas() -> None:
    schema_files = _schema_files()
    if not schema_files:
        pytest.skip("not_run: ContractV1/VerdictV1/ObservationV1 are not present on main")

    import jsonschema

    examples = sorted(EXAMPLES.glob("*.json"))
    assert examples, "schema files exist but app/examples has no JSON examples"
    schemas = {}
    for schema_path in schema_files:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schemas[schema_path.name.removesuffix(".schema.json").lower()] = schema
    for example in examples:
        payload = json.loads(example.read_text(encoding="utf-8"))
        stem = example.stem.lower()
        matched = next((schema for name, schema in schemas.items() if name in stem), None)
        assert matched is not None, f"no schema matched example {example.name}"
        jsonschema.validate(payload, matched)
