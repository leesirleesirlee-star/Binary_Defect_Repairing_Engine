# ADR 0005: the runner's terminal state and its evidence export

- **Status:** accepted
- **Date:** 2026-11-24
- **Deciders:** M1 (runner/lead); M2 and M3 informed
- **Related:** PR #56 (G4 console), PR #48/#52 (runner stages), `docs/interfaces/gui-events-v1.md`, G4 gate

## Context

The merged runner (#48/#52) executes `collect -> freeze -> analyze -> decision ->
repair -> verify` and left `audit` and `export` permanently `skipped` with
`stage_not_wired`. Because a run with a skipped stage ended `failed`, the G4
console completed a real repair — the verifier returned
`verified_against_stated_criteria`, the artifacts downloaded — while `run_end`
still said `failed` with `reason_code = stages_not_wired`. The console then had
to explain that its own terminal record disagreed with its verdict.

Two facts drove the decision:

1. The **audit is signed evidence, not work this run repeats**. The G2 record
   (three runs, rubric scores, selected plan) is frozen and the runner consumes
   the persisted `proceed` decision. Calling that stage `stage_not_wired` is
   false: the runner *does* honor the signed record; it just never runs a new
   audit.
2. **Export is runner work** and was simply missing. Without it the demo's
   evidence bundle had no hash manifest, and no run could ever be complete.

## Decision

1. **The `audit` step is never `completed` by the runner.** When a persisted
   decision exists it is `skipped` with the reason code
   `satisfied_by_signed_g2`; without a decision it is `skipped` with
   `decision_missing`. The step list therefore still shows that this run did not
   re-run the audit.
2. **The `export` stage is wired.** It writes
   `var/artifacts/<task>/export/bundle-manifest.json`: the verdict word and
   verdict hash, and every artifact the run produced with its sha256 and size. It
   never recomputes or re-words the verdict; an absent or schema-invalid
   `verdict.json` is a refusal (`export_verdict_missing` /
   `export_verdict_invalid`), never a fabricated bundle.
3. **`run_end.execution = "completed"` now means: the stages this run is
   required to execute finished.** Required = analyze, the persisted decision,
   repair, verify, export. The skipped `audit` is visible in the same journal as
   `skipped (satisfied_by_signed_g2)`, and `run_end.steps_taken` counts only
   completed steps (usually 7 of 8). A blocked or failed stage keeps
   `execution = "failed"` with its reason code; a cancelled run keeps
   `"cancelled"`.
4. **The terminal record is derived, not asserted.** The runner sets
   `completed` only after the export stage wrote its manifest; there is no path
   that marks a run complete with a skipped or failed required stage.

## Consequences

- The GUI can render the real eight-step checklist and the persisted `run_end`
  without contradicting the verdict; the "5/5 steps, verify completed" projection
  in the current console becomes a defect to remove (G4 review).
- `gui-events-v1.md` gains the two reason codes and the rule that
  `run_end.execution = completed` requires export; the event envelope is
  unchanged.
- Existing tests that expected `reason_code = stages_not_wired` are updated to
  expect the real outcome; a successful run now writes 7 changed files
  (2 analysis + 3 repair + 1 verdict + 1 export).
- `export/bundle-manifest.json` is a new downloadable artifact; it is not a
  verdict and must not be rendered as one.
- `audit` remains provider- and key-free in the runner: no key is read, no model
  is called, and the G2 record stays the only audit evidence.
