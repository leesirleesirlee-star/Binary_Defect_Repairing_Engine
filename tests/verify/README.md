# Verify tests

Owner: M3. Tests for the deterministic V0-V5 verifier and the verdict writer.

`test_verifier.py` uses the frozen fixture bytes and synthetic
`ObservationV1`/`EditManifestV1` documents (the manifest is applied in memory;
nothing is executed). It covers the pass path, every failure/`not_run` path, the
`unsupported`/`error` envelopes, the CLI, `VerdictV1` schema validation and the
reproducible `verdict_sha256`. A missing observation must produce `not_run` or
`unverified`, never `verified_against_stated_criteria`.

```bash
python -m pytest -q -m "not guest" tests/verify
```
