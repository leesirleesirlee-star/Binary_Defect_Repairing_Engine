# Verify tests

Owner: M3. Tests for the deterministic V0-V5 verifier and the verdict writer.

`test_verifier.py` uses the frozen fixture bytes and synthetic
`ObservationV1`/`EditManifestV1` documents (the manifest is applied in memory;
nothing is executed). It covers the pass path, every failure/`not_run` path, the
`unsupported`/`error` envelopes, the CLI, `VerdictV1` schema validation and the
reproducible `verdict_sha256`. A missing observation must produce `not_run` or
`unverified`, never `verified_against_stated_criteria`.

## Live observations and V4 coverage

The G4.1 live path adds two constraints covered here:

- The committed `docs/plan/evidence/g3/observations-candidate-wsl2.json` must
  validate against `ObservationV1`, bind `binary.sha256` to the G3 candidate
  (`c010c006...b28`), and contain all nine frozen case ids.
- A live-style observation document is still judged by the same V0-V5 rules; a
  candidate-hash mismatch fails V0 and cannot produce
  `verified_against_stated_criteria`.

V4 recognises the two declared guard layouts:

```text
legacy 69-byte guard
G2-selected 90-byte guard (G3 candidate)
```

Any other layout is `not_run`; the verifier then returns `unverified`, never a
pass. `test_unrecognised_guard_layout_makes_v4_not_run` and the selected-plan
tests pin that rule; `live-ai-run-v1` does not weaken it for live plans.


```bash
python -m pytest -q -m "not guest" tests/verify
```
