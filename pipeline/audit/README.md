# `pipeline/audit` - three-run audit and report

Owner: M4 (`audit` module). Gate: G2.

## Input

- Frozen fixture, contract and PoC.
- `DisassemblyViewV1`.
- Three `FixPlanV1` runs.
- The rubric in `docs/plan/03-fixture-and-ai-audit-spec.md`.

## Output

- Raw responses (key removed) and their hashes.
- A score table per run.
- A written report with the decision `proceed` / `iterate` / `change_scope`.

## Rules

- The contract, corpus and rubric are fixed before the runs. They do not change
  to improve a score.
- Record schema-valid, usable artifact and correctness established separately.
- Two reviewers (M1 contract/evidence, M5 implementability); M3 confirms the
  corpus did not change.
- No cherry-picking: every run stays in the table, including invalid JSON.
- No model output in the report is presented as evidence of execution.
