# GUI examples

These files are the published v0 artifact examples copied from
`schemas/examples/` on PR #22 (`m1/schemas-v0`). They let the read-only GUI
develop and test against the exact M1 shapes before the schemas are merged.

| File | Schema |
|---|---|
| `ContractV1.example.json` | `ContractV1.schema.json` |
| `FixPlanV1.example.json` | `FixPlanV1.schema.json` |
| `ObservationV1.example.json` | `ObservationV1.schema.json` |
| `VerdictV1.example.json` | `VerdictV1.schema.json` |
| `EditManifestV1.example.json` | `EditManifestV1.schema.json` |

They are read-only fixtures, not GUI-authored data. Canonical examples stay in
`schemas/examples/`; M1 owns them. `tests/app/test_examples.py` validates these
copies against the matching schemas when the schema files are present.

The four-screen examples wait for `FixtureManifestV1`, `CaseSetV1`,
`DisassemblyViewV1`, `FindingV1`, `TaskViewV1` and `EvidenceBundleV1` at their
roadmap gates (G1/G2/G4).
