## Summary

<!-- What changed and why, in 2-4 sentences. -->

## Issue / module / gate

Closes #<!-- issue number -->

- Module label (exactly one): `module:<!-- contract | infra | fixture | guest | verify | analysis | ai | audit | repair | gui -->`
- Gate: `<!-- G0 | G1 | G2 | G3 | G4 -->`

The PR must carry the same `module:<id>` label as the issue. CI runs
`scripts/check_modules.py` and fails if a changed file is outside that module.

## Evidence

Commands run and observed output. For fixture, audit or repair work, include the
artifact path and its SHA-256.

```text
$ command
observed output
```

## Checks

- [ ] `ruff check .`
- [ ] `python -m pytest -q -m "not guest"`
- [ ] `python scripts/check_modules.py --base origin/main`
- [ ] No secrets, client binaries, private logs or keys
- [ ] No file outside the declared module
- [ ] Docs updated in the module's docs folder
- [ ] The verdict is unchanged, or the change is documented and reviewed

## Acceptance impact

<!-- Which contract criteria, observations, audit scores or verdict states can
change? If none, say "none". -->

## Rollback

<!-- How to revert this change safely. -->
