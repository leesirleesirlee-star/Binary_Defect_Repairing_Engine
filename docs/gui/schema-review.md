# GUI schema review for the four screens

Status: M2 review against merged PR #22 (`fd2b784`) under the **roadmap
authority**. The roadmap section 5 vocabulary and the `schemas/README.md` naming
rule win over stale text in issue #2.

The four screens themselves move to #12. This document records what each screen
needs, the persisted JSON path it uses, and the gaps that remain at later gates.

## Authority decisions

- **Verdict vocabulary is the roadmap six-word set**:
  `verified_against_stated_criteria`, `rejected`, `unverified`, `unsupported`,
  `error`, `not_run`. Issue #2's three-word acceptance text is stale and must be
  corrected; no `not_verified` alias is added.
- **Schema filenames follow `schemas/README.md`**:
  `<Name>V<major>.schema.json`. Issue #2's lowercase filenames are stale.
- **`not_run` is a verdict/criterion state, never a success.** It comes from
  `VerdictV1.verdict` or `VerdictV1.criteria[].status`. A required case missing
  from `ObservationV1` is not inferred from `timed_out`; that join needs
  `CaseSetV1` at G1.
- **Contract revision is file identity, not a new JSON field.** The Task screen
  displays the SHA-256 of the persisted contract file; `app/loader.digest()`
  computes it without inventing a schema property. `schema_version` remains the
  schema major version.

## Screen field lists

### 1. Task screen

| Field needed | Schema | Schema path | State |
|---|---|---|---|
| fixture id | `ContractV1` | `fixture_id` | available in PR #22 |
| original binary hash | `ContractV1` | `binary_sha256` | available in PR #22 |
| target function | `ContractV1` | `target_function` | available in PR #22 |
| contract revision | `ContractV1` file identity | SHA-256 via `app/loader.digest()` | convention, no schema change |
| fixture identity, ELF facts, reserved R-X range | `FixtureManifestV1` | `fixture_id`, `binary.sha256`, `elf.*`, `segments[]`, `reserved_range` | available on main |
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
| original/candidate case rows | `ObservationV1` | `cases[].id`, `cases[].argv_sha256`, `cases[].exit_code`, `cases[].signal`, `cases[].stdout_b64`, `cases[].stderr_b64`, `cases[].duration_ms`, `cases[].timed_out` | available in PR #22 |
| case id, kind, argv/stdin | `CaseSetV1` | `cases[].id`, `cases[].kind`, `cases[].argv`, `cases[].stdin` | available on main |
| expected original/candidate behavior | `CaseSetV1` | `cases[].expected_original`, `cases[].expected_candidate` | available on main |
| required-but-missing case -> `not_run` | `CaseSetV1` + `ObservationV1` join | GUI rule: a required case id absent from `ObservationV1.cases[]` renders `not_run` | documented, M2 owns implementation at #12 |

### 4. Evidence screen

| Field needed | Schema | Schema path | State |
|---|---|---|---|
| original/candidate hashes | `VerdictV1` | `original_sha256`, `candidate_sha256` | available in PR #22 |
| limitations | `VerdictV1` | `limitations[]` | available in PR #22 |
| artifact descriptors | `EvidenceBundleV1` | not published (G4) | blocked on M1 |
| artifact hashes | `EvidenceBundleV1` | not published (G4) | blocked on M1 |
| download links | `EvidenceBundleV1` | not published (G4) | blocked on M1 |
| missing-artifact state | `EvidenceBundleV1` | not published (G4) | blocked on M1 |

## Gaps to file on #3

1. `DisassemblyViewV1` and `FindingV1` (G2, M4) must carry the function slice,
   call site and defect location without source paths. Analysis field review is
   blocked until then.
2. `TaskViewV1` (G4, M2) and `EvidenceBundleV1` (G4, M1) are required by the
   Task/Evidence screens; their field reviews remain open until published.
3. The Verification join rule is now explicit: a case id required by
   `CaseSetV1` but absent from `ObservationV1.cases[]` renders `not_run`; never
   infer it from `timed_out`. #12 owns the implementation and a test.
4. Issue #2's verdict vocabulary and schema filenames are stale; correct them to
   the roadmap/`schemas/README.md` authority in the issue.

No GUI field has been invented to cover an absent schema field. The contract
revision is rendered from persisted file bytes, not added to `ContractV1`.

## Read-only data layer and examples

`app/loader.py` implements `load(path, *, root=None) -> dict` and
`digest(path, *, root=None) -> str`:

- resolves every path below the repository data root;
- rejects absolute paths outside the root, `..` escapes, NUL bytes, non-JSON
  files and symlink escapes;
- raises `ArtifactMissing` for a missing file, `ArtifactInvalid` for malformed or
  non-object JSON and `ArtifactUnsafe` for path violations;
- returns the decoded object unchanged and has no verdict or schema logic.

`app/examples/` contains the seven merged-PR #22 artifact examples copied for GUI
development. `tests/app/test_examples.py` validates them against
`schemas/*.schema.json` when the schema files are present. It validates all seven examples against `schemas/*.schema.json` after main merged
PR #22.

`app/render.py` renders missing values as `missing`, observation statuses
verbatim and a verdict only from the persisted `VerdictV1.verdict` field.
Observations alone cannot produce `verified_against_stated_criteria`.
