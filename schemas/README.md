# Schemas

Owned by M1 (`contract` module). JSON Schema 2020-12. Every schema has an
`examples/` file and a test under `tests/contract/`.

| Schema | Producer | Consumer | Frozen |
|---|---|---|---|
| `ContractV1` | M1 | all | G1 |
| `FixtureManifestV1` | M3 | M4, M5 | G1 |
| `CaseSetV1` | M3 | verifier | G1 |
| `DisassemblyViewV1` | M4 | M5, M2 | G2 |
| `FindingV1` | M4 | M1, M5, M2 | G2 |
| `FixPlanV1` | M4 | M1, M3, M5 | G2 |
| `AuditReportV1` | M4 | M1 | G2 |
| `EditManifestV1` | M5 | M3, M2 | G3 |
| `CandidateV1` | M5 | M3, M2 | G3 |
| `ObservationV1` | M3 | M2, M1 | G3 |
| `VerdictV1` | M3 | M2, M1 | G3 |
| `TaskViewV1` | M2 | GUI | G4 |
| `EvidenceBundleV1` | M1 | report | G4 |

## Rules

- A schema change is an ADR plus an M1 PR; all consumers review.
- Additive fields bump the minor version; removing or renaming bumps the major
  version. The old schema stays in the repository.
- `schema_version` is an integer in every payload.
- Examples are validated by `tests/contract/`.
- No schema carries source text, source paths, keys or client data.

## Naming

`<Name>V<major>.schema.json`, for example `ContractV1.schema.json`.
