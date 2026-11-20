# `pipeline/verify` - deterministic checks and verdict writer

Owner: M3 (`verify` module). Gate: G3.

## Input

- Original ELF and candidate ELF (hashes).
- `EditManifestV1`.
- Frozen `CaseSetV1`.
- `ObservationV1` for original and candidate.
- `ContractV1`.

## Output

- `VerdictV1` in the fixed vocabulary:
  `verified_against_stated_criteria`, `rejected`, `unverified`, `unsupported`,
  `error`.
- Per-check rows, including `not_run`.

## Checks (MVP2)

| Check | What it proves |
|---|---|
| V0 identity | hashes match the manifest; the source did not enter the inputs |
| V1 structure | ELF valid; only manifest edits; no W+X; no new import; cave in R-X |
| V2 valid behavior | every valid case matches the original's stdout and exit code |
| V3 invalid behavior | exact stderr, exit 1, empty stdout, no signal; PoC no longer crashes |
| V4 boundary | 31 accepted, 32 rejected; the guard checks before `strcpy` |

V5 re-apply reproducibility is optional for MVP2.

## Rules

- This module is the **only** writer of a verdict.
- Never import `pipeline/ai`, `pipeline/audit` or `pipeline/repair`.
- Never read the AI plan or the source.
- A missing observation is `not_run`, never a pass.
- `verified_against_stated_criteria` requires every required check on matching
  hashes; the scope is the written contract only.
