# PR submission checklist (M5 dry-run)

Status: **not submitted**. The local branch cannot be pushed until M1 fixes the
repair owner in `modules.json`/`CODEOWNERS` and PR #14 is merged. This checklist
is a preflight for the eventual PR.

## Before commit

- [ ] All changes are under `pipeline/repair/`, `tests/repair/`, `docs/repair/`.
- [ ] No `fixture`, `contract`, `cases`, `schemas`, `pipeline/verify` or `app`
      file was modified.
- [ ] No `candidate.elf` exists anywhere in the workspace.
- [ ] Every manifest has `dry_run: true`, `verdict: null`, and
      `preview.candidate_written: false`.
- [ ] No test or tool executed the fixture/candidate on the host.
- [ ] Error string, input boundary and exit codes were not changed.
- [ ] The new fixture, if not yet published, is still treated as unavailable;
      no address was guessed.

## Local verification

```bash
python -m pytest -q tests/repair
python -m pytest -q -m "not guest"
ruff check .
python scripts/check_modules.py --base origin/main --labels "module:repair"
```

Expected current results:

```text
pytest tests/repair                 79 passed
pytest -q -m "not guest"            108 passed
ruff check .                        All checks passed
module check                        OK: every changed file matches module repair
```

## Commit split

- [ ] `feat(repair): add elf64 core + cave finder dry-run tools`
- [ ] `feat(repair): add patch writer + self-check with manifest output`
- [ ] `test(repair): add unit tests covering boundary, reversibility, determinism`
- [ ] `docs(repair): add dry-run docs, guard ABI and preflight notes`

Each commit must be independently reviewable and must not include unrelated
files.

## PR template (five required items)

**What changed:** M5 dry-run tooling only: ELF64 parser, cave finder (explicit
range and all-R-X-segment modes), guard/patch manifest writer, structural
self-check and preflight framework. No candidate is produced.

**Related issue:** #10.

**Gate:** P0 tooling / G0 preparation; this PR does not claim G2 or G3 and does
not apply a repair.

**Run results:** `pytest tests/repair` 79 passed; `pytest -q -m "not guest"` 108
passed; `ruff check .` passed.

**Own scope:** Yes. Only `pipeline/repair/`, `tests/repair/`, `docs/repair/`.

## PR body warning

The PR body must explicitly say:

> Dry-run tool set. No real fixture was modified, no candidate is generated and
> no verdict is included.

## After merge

- [ ] Pull latest `main` and rerun the full host test suite.
- [ ] Run `validate_fixture.py` against the new fixture **only after** M3
      publishes it.
- [ ] Attach the preflight JSON report to issue #10.
- [ ] Wait for G2 approval; do not apply the manifest to the real fixture.
