# GUI schema review for the four screens

Status: G0 draft. Owner: M2 (GUI). Input schemas: `ContractV1`, `VerdictV1`,
`ObservationV1` (M1). The files are not present on `main` at the time of this
review, so exact JSON pointers cannot be filled in yet and no GUI field has been
invented to cover a gap.

## Why this exists

The GUI renders persisted JSON only. It must not chase backend code and it must
not compute a verdict, pass rate or success label. The four screens are deferred
to #12; this review fixes the data each screen needs before the schema freeze.

## Screen field lists

### 1. Task screen

| Field needed | Source schema | Schema path | State |
|---|---|---|---|
| fixture identity | `FixtureManifestV1` | unresolved (schema absent) | gap |
| original ELF hash (sha256) | `FixtureManifestV1` | unresolved | gap |
| contract revision | `ContractV1` | unresolved | gap |
| run action availability | not a persisted field; route/action binding | n/a | GUI-only |

### 2. Analysis screen

| Field needed | Source schema | Schema path | State |
|---|---|---|---|
| disassembly view | `DisassemblyViewV1` | unresolved | gap |
| finding / defect location | `FindingV1` | unresolved | gap |
| AI plan card | `FixPlanV1` | unresolved | gap |
| assumptions | `FixPlanV1` | unresolved | gap |
| uncertainties | `FixPlanV1` | unresolved | gap |
| human approve control | GUI action state, bound separately | n/a | GUI-only |

### 3. Verification screen

| Field needed | Source schema | Schema path | State |
|---|---|---|---|
| original/candidate case table | `CaseSetV1` | unresolved | gap |
| per-case observations | `ObservationV1` | unresolved | gap |
| 31/32 boundary evidence | `ObservationV1` / `CaseSetV1` | unresolved | gap |
| verdict banner | `VerdictV1` | unresolved | gap |
| `not_run` status | `ObservationV1` | unresolved | gap |

### 4. Evidence screen

| Field needed | Source schema | Schema path | State |
|---|---|---|---|
| artifact descriptors | `EvidenceBundleV1` | unresolved | gap |
| artifact hashes | `EvidenceBundleV1` | unresolved | gap |
| download links | `EvidenceBundleV1` | unresolved | gap |
| limitations | `EvidenceBundleV1` / `VerdictV1` | unresolved | gap |
| missing-artifact state | `EvidenceBundleV1` | unresolved | gap |

## Gaps to file on issue #3 before G1

1. `TaskViewV1` (M2-owned, listed in `schemas/README.md`) has no draft; its task
   identity/hash/contract fields and `schema_version` are undefined.
2. `DisassemblyViewV1` and `FindingV1` must expose the function slice, call site
   and defect location without source paths.
3. `FixPlanV1` must expose assumptions and uncertainties as separate fields; the
   analysis screen cannot label them if the schema only carries prose.
4. `CaseSetV1` + `ObservationV1` need a stable case id and a per-case status
   vocabulary that includes `not_run` and `unsupported` verbatim.
5. `VerdictV1` must contain exactly one outcome field; the GUI must not derive
   `verification` from observations.
6. `EvidenceBundleV1` needs an artifact descriptor with path/hash/missing state;
   a missing artifact must be representable without a success-like placeholder.
7. `EvidenceBundleV1` or `VerdictV1` must carry limitations as structured data,
   not only a free-text sentence.

These gaps are unresolved until M1 freezes the schemas. No GUI field has been
invented to fill them.

## Read-only data layer

`app/loader.py` implements `load(path, *, root=None) -> dict`:

- resolves every path below the repository root;
- rejects absolute paths outside the root, `..` escapes, NUL bytes, non-`.json`
  files and symlink escapes;
- raises `ArtifactMissing` for a missing file, `ArtifactInvalid` for malformed or
  non-object JSON and `ArtifactUnsafe` for path violations;
- returns the decoded object unchanged and has no verdict or schema logic.

`app/render.py` is the honesty boundary for the future four screens. It renders
missing values as `missing`, observation statuses verbatim and a verdict only
from a persisted `outcome`; observations alone cannot produce
`verified_against_stated_criteria`.

## Blocked acceptance items

- `app/examples/*.json` and schema validation are `not_run`: `ContractV1`,
  `VerdictV1` and `ObservationV1` are absent on `main`. `tests/app/test_examples.py`
  reports that as `not_run`; no guessed example was committed.
