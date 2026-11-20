# Interfaces: frozen handoffs between seats

A handoff is a JSON artifact with a schema and a SHA-256. A chat message is only
a notification; it is not a handoff.

| ID | Artifact | Producer | Consumer | Schema | Frozen |
|---|---|---|---|---|---|
| H1 | `contract.json` | M1 (review M3) | M2, M3, M4, M5 | `ContractV1` | G1 |
| H2 | `fixture-manifest.json` | M3 | M4, M5 | `FixtureManifestV1` | G1 |
| H3 | `cases/{valid,invalid,poc}.json` | M3 | verifier; PoC only to M4 | `CaseSetV1` | G1 |
| H4 | `disassembly.json` + finding | M4 | M1, M5, M2 | `DisassemblyViewV1`, `FindingV1` | G2 |
| H5 | `fix-plan.json` (3 runs) | M4 | M1, M3, M5 | `FixPlanV1` | G2 |
| H6 | `audit-report.md` + raw responses | M4 | all | report template | G2 |
| H7 | `candidate.elf` + `edit-manifest.json` | M5 | M3, M2 | `EditManifestV1`, `CandidateV1` | G3 |
| H8 | `observations-*.json` | M3 | M2, M1 | `ObservationV1` | G3 |
| H9 | `verdict.json` | M3 verifier | M2, M1 | `VerdictV1` | G3 |
| H10 | `evidence-bundle.json` | M1 assembles | M2, report | `EvidenceBundleV1` | G4 |

## Rules

1. A consumer does not start until the producer commits the artifact with a
   SHA-256.
2. A frozen artifact changes only with a new version and an ADR. The old version
   stays readable.
3. The verifier consumes H7 and H8, not a chat description of the patch.
4. The GUI consumes H4-H9 as persisted JSON; it never imports the producer's
   code to recompute a result.
5. A model output (H5) is untrusted display data. It never changes the contract,
   the corpus, the tools or the verdict.

## Location

- Schemas: `schemas/`.
- Runtime artifacts: `var/` (gitignored), copied into evidence only by M1.
- Gate records: `docs/plan/records/`.
