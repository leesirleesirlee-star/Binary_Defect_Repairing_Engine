# ADR 0006: the live AI mode is additive evidence, not a new gate

- **Status:** accepted
- **Date:** 2026-11-24
- **Deciders:** M1 (lead/contract); M2, M3, M4, M5 informed
- **Related:** ADR 0005 (runner terminal state), PR #56 (G4 console), issues #60-#68 (G4.1)

## Context

G4 ships a console that replays the signed G2 three-run audit: the runner marks
`audit` as `skipped (satisfied_by_signed_g2)`, applies the frozen
`docs/audit/fix-plan-v1.json`, and verifies against M3's recorded WSL2 guest
observations. That is the deterministic acceptance path and it stays.

The provider transport (`pipeline/ai/provider.py`), the three-run harness
(`pipeline/audit`) and the key store (`app/assistant_key.py`) already exist, but no
runtime path calls them: the console never triggers a model call and the runner
never reads a key. For the final demonstration we want the AI step to be visible
and causal: a live three-run audit, a human choice among the three plans, a live
WSL2 guest run, and the same deterministic verifier.

## Decision

1. **Two modes, one evidence rule.** `audit_mode = "signed"` (default, offline,
   the G4 acceptance path) and `audit_mode = "live"` (this ADR). The live mode is
   additive: it does not rewrite the G2 record, the frozen contract, the corpus or
   any G1-G3 hash.
2. **The audit runs in the API host, never in the runner.** The API spawns
   `python -m pipeline.audit` as a child with the model pinned and the key taken
   from `assistant_key`, injected **only into that child's environment**. The
   runner, the UI, the guest and the logs never see the key. The runner consumes
   the three recorded plans and never calls a model.
3. **The human selects; the machine validates.** The three plans are shown with
   schema status, critical errors and a canonical plan hash; the human selects
   one. The selection records `selected_plan` (source, run index, path, file and
   canonical hashes) and the `proceed` decision. There is no preselection and no
   automatic fallback to the signed plan.
4. **The live plan is legitimate evidence for this run, even if it differs from
   the signed one**, as long as it stays inside the frozen `allowed_edits`. The
   repair CLI is plan-driven; the verifier judges the resulting candidate against
   the same frozen contract and corpus.
5. **The live guest is the only executor.** `guest/live_guest.py` copies the
   original and the candidate into a fresh directory inside Ubuntu, runs M3's
   `run_cases.py` twice, and pulls the observations plus the guest environment
   back. The host never executes an ELF. The verifier binds
   `candidate_sha == observations.binary.sha256` (V0); a mismatched or missing
   observation file is a refusal, never a pass.
6. **The verifier is unchanged and remains the only writer of the verdict.** The
   six-word vocabulary is untouched. V4 recognises the declared guard layouts; a
   live plan whose layout is not recognised yields `unverified` and that is the
   honest result — the success rule is never weakened to make the demo green.
7. **Every failure has an honest path.** No key, no WSL, provider error, audit
   timeout, invalid runs, guest failure or plan outside `allowed_edits` end in a
   stable code and, when relevant, the option to replay the signed plan. The
   console never silently substitutes the signed plan for a live one.

## Consequences

- New task fields (`audit_mode`, `live_guest`, `live_audit`, `selected_plan`), three
  API endpoints, a guest driver CLI, an audit summary output, a canonical plan
  hash, and runner reason codes — all fixed in
  `docs/interfaces/live-ai-run-v1.md`.
- No schema change, no frozen-hash change, no gate re-opening. G4 remains signed;
  the live run is recorded as G4.1 demo evidence with its own commands and hashes.
- CI stays key-free: the live path is exercised with a fake child in tests and a
  real WSL2 run on M3's machine; the no-key fallback is tested.
- WSL2 shares the host network, so the guest is weaker isolation than a
  disposable VM; this is documented in `docs/guest/live-wsl2.md` and the demo
  record.
