# GUI tests

Owner: M2. Render each screen from example JSON; assert `not_run` is verbatim,
missing artifacts are shown as missing and no success label appears without a
verdict.

Current tests:

- `test_loader.py`: the read-only loader returns persisted JSON verbatim and
  rejects traversal, absolute escapes, symlinks, non-JSON files, malformed JSON
  and non-object roots. Missing files are a distinct `ArtifactMissing`.
- `test_honesty.py`: `not_run` and `unsupported` are verbatim; missing
  observations/artifacts are `missing`; no success label appears without a
  persisted verdict.
- `test_examples.py`: validates `app/examples/*.json` against
  `schemas/*.schema.json`. At G0 the contract schemas are not on `main`, so the
  test reports `not_run` instead of inventing fields.

```bash
python -m pytest -q tests/app
```
