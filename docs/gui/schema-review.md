# GUI schema review for the four screens

Status: M2 review against PR #22 (`m1/schemas-v0`). The review is intentionally
incomplete: the PR publishes `ContractV1`, `FixPlanV1`, `ObservationV1`,
`VerdictV1` and `EditManifestV1`; the schemas owned by other gates are still
absent. No GUI field has been invented to cover a missing schema field.

The four screens themselves move to #12. This document records what each screen
needs, the persisted JSON path it would use, and the gaps that must be filed on
issue #3 before G1 freezes.

## Screen field lists

### 1. Task screen

| Field needed | Schema | Schema path | State |
|---|---|---|---|
| fixture id | `ContractV1` | `fixture_id` | available in PR #22 |
| original binary hash | `ContractV1` | `binary_sha256` | available in PR #22 |
| target function | `ContractV1` | `target_function` | available in PR #22 |
| contract revision | `ContractV1` | none | **gap** |
| ELF metadata / fixture manifest identity | `FixtureManifestV1` | not published (G1) | blocked on M3 |
| run action | no persisted field | GUI action binding | GUI-only |

### 2. Analysis screen

| Field needed | Schema | Schema path | State |
|---|---|---|---|
| plan id and contract binding | `FixPlanV1` | `plan_id`, `contract_sha256` | available in PR #22 |
| model and prompt identity | `FixPlanV1` | `model.provider`, `model.name`, `model.prompt_sha256` | available in PR #22 |
| target and edits | `FixPlanV1` | `target.function`, `target.edit_site_vaddr`, `edits[]` | available in PR #22 |
| assumptions | `FixPlanV1` | `assumptions[]` | available in PR #22 |
| uncertainties | `FixPlanV1` | `uncertainties[]` | available in PR #22 |
| disassembly view | `DisassemblyViewV1` | not published (G2) | blocked on M4 |
| finding / defect location | `FindingV1` | not published (G2) | blocked on M4 |
| human approve control | no persisted field | GUI action state | GUI-only |

### 3. Verification screen

| Field needed | Schema | Schema path | State |
|---|---|---|---|
| original hash | `VerdictV1` | `original_sha256` | available in PR #22 |
| candidate hash | `VerdictV1` | `candidate_sha256` | available in PR #22 |
| contract binding | `VerdictV1` | `contract_sha256` | available in PR #22 |
| verdict label | `VerdictV1` | `verdict` | available in PR #22 |
| per-criterion status | `VerdictV1` | `criteria[].id`, `criteria[].required`, `criteria[].status`, `criteria[].evidence_sha256` | available in PR #22 |
| coverage | `VerdictV1` | `coverage.cases_total`, `coverage.cases_run`, `coverage.unmeasured` | available in PR #22 |
| limitations | `VerdictV1` | `limitations[]` | available in PR #22 |
| original/candidate case rows | `ObservationV1` | `cases[].id`, `cases[].argv_sha256`, `cases[].exit_code`, `cases[].signal`, `cases[].stdout_b64`, `cases[].stderr_b64`, `cases[].duration_ms`, `cases[].timed_out` | partially available |
| explicit case `not_run` state | `ObservationV1` | none | **gap** |
| case input and expected boundary data | `CaseSetV1` | not published (G1) | blocked on M3 |
| 31/32 boundary identity | `CaseSetV1` / `ObservationV1` | unresolved | **gap** |

### 4. Evidence screen

| Field needed | Schema | Schema path | State |
|---|---|---|---|
| original/candidate hashes | `VerdictV1` | `original_sha256`, `candidate_sha256` | available in PR #22 |
| limitations | `VerdictV1` | `limitations[]` | available in PR #22 |
| artifact descriptors | `EvidenceBundleV1` | not published (G4) | blocked on M1 |
| artifact hashes | `EvidenceBundleV1` | not published (G4) | blocked on M1 |
| download links | `EvidenceBundleV1` | not published (G4) | blocked on M1 |
| missing-artifact state | `EvidenceBundleV1` | not published (G4) | blocked on M1 |

## Gaps to file on issue #3 before G1 freeze

1. **`ObservationV1` has no per-case status.** `cases[]` requires
   `exit_code`, `signal`, `timed_out`, stdout/stderr and duration, but no explicit
   `ran` / `not_run` field. A GUI cannot render `not_run` verbatim for a case
   without inventing a mapping from `timed_out` or null exit code. Add a
   case-level status vocabulary (for example `ran`, `not_run`, `timed_out`,
   `error`) or an explicit `not_run` boolean.
2. **`ContractV1` has no contract revision.** The Task screen needs a contract
   revision; `schema_version` is a schema major version, not the revision of
   this contract file. Define a revision field or document that the GUI displays
   the contract file's content hash computed outside the schema.
3. **`ContractV1` has no contract digest**, while `VerdictV1.contract_sha256`
   binds a verdict to a contract. The Task screen should show the bound contract
   identity; define how the contract file is canonicalized/hashed.
4. **`ObservationV1` has no case input/expected data** and `CaseSetV1` is not
   published. The 31/32 boundary and expected behaviour cannot be rendered from
   observations alone. Record a `CaseSetV1` requirement at G1.
5. **The verdict vocabulary conflicts.** Issue #2 acceptance says exactly
   `verified_against_stated_criteria` / `not_verified` / `not_run`; PR #22 and
   roadmap section 5 use six words
   (`verified_against_stated_criteria`, `rejected`, `unverified`, `unsupported`,
   `error`, `not_run`). Decide the single vocabulary before either issue or
   schema freezes; the GUI cannot support both.
6. **Issue #2 filenames conflict with `schemas/README.md`.** Issue #2 says
   `schemas/contract.schema.json` and `schemas/fix-plan.schema.json`; the PR uses
   `ContractV1.schema.json` and `FixPlanV1.schema.json`. Update issue #2 or add
   aliases before closing it.
7. **`TaskViewV1` and `EvidenceBundleV1` are not in PR #22.** Both are needed by
   the four-screen flow; `TaskViewV1` is M2-owned at G4 and
   `EvidenceBundleV1` is M1-owned at G4. The field review for Task/Evidence
   cannot complete until their schemas exist.

## Read-only data layer

`app/loader.py` implements `load(path, *, root=None) -> dict`:

- resolves every path below the repository data root;
- rejects absolute paths outside the root, `..` escapes, NUL bytes, non-`.json`
  files and symlink escapes;
- raises `ArtifactMissing` for a missing file, `ArtifactInvalid` for malformed or
  non-object JSON and `ArtifactUnsafe` for path violations;
- returns the decoded object unchanged and has no verdict or schema logic.

`app/render.py` renders missing values as `missing`, observation statuses
verbatim and a verdict only from the persisted
`VerdictV1.verdict` field. Observations alone cannot produce
`verified_against_stated_criteria`.

## Remaining #3 acceptance items after PR #22

- `app/examples/*.json` validation is blocked until the additional schemas land
  and PR #22 is merged; `tests/app/test_examples.py` reports that as `not_run`
  rather than validating guessed fields.
- The field review above is complete for the five artifacts in PR #22; the
  evidence and task-view rows remain blocked on their G4 schemas.
