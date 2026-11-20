# `pipeline/repair` - cave finder, patch writer, edit manifest

Owner: M5 (`repair` module). Gate: G3.

## Input

- The original ELF.
- The approved `FixPlanV1` from G2.
- `ContractV1` (allowed edits).

## Output

- `candidate.elf`.
- `EditManifestV1`: every offset, vaddr, original bytes, new bytes and reason.
- A reproducible patch script.

## Rules

- **Do not apply a fix to the fixture before G2 approves a plan.** Generic ELF
  editing primitives and dry-run manifests are allowed during G1/G2.
- Only the edits in the approved plan and the contract: one 5-byte redirect, a
  cave in the existing R-X segment, no new segment, no new import, no W+X.
- The valid path must keep `strcpy` semantics and the return value; the invalid
  path writes the exact stderr line and exits 1.
- Never read `pipeline/verify/` or `fixtures/**/cases/`.
- The candidate is handed to M3; M5 does not sign the verdict.
