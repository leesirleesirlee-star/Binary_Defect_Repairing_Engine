# Golden manifest snapshots

These snapshots exist **only** to detect unintended changes in the deterministic
output of the M5 dry-run tools. They are not repair evidence, not a candidate and
not a verdict.

## Canonical hash

`manifest_sha256` hashes the manifest JSON after removing:

- `created_at` (optional evidence metadata);
- `manifest_sha256` itself (self-reference);
- local `original.path` / `contract.path` values (environment metadata, not
  repair facts).

The payload is serialized with `sort_keys=True`, compact separators
`(",", ":")` and UTF-8. The same ELF, patch site, cave and guard must produce
the same hash across runs and machines.

## Update policy

- A failing golden test must be investigated; do **not** auto-update the
  snapshot.
- An intentional format/tool change requires a reviewed update to
  `manifest-cases.json` and a note in the change description.
- The no-tail case intentionally has no manifest hash: the tool must return
  `unsupported` instead of inventing one.

## Run

```bash
python -m pytest -q tests/repair/test_golden_manifest.py
```
