# PR submission checklist (M5 dry-run)

Status: **PR #19 opened** at
<https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine/pull/19>;
waiting for M1 review/merge. PR #14 (ADR 0001) is still open and M3's new
fixture is not published. This checklist records what was verified before push.

## Before commit

- [x] All changes are under `pipeline/repair/`, `tests/repair/`, `docs/repair/`.
- [x] No `fixture`, `contract`, `cases`, `schemas`, `pipeline/verify` or `app`
      file was modified.
- [x] No `candidate.elf` exists anywhere in the workspace.
- [x] Every manifest has `dry_run: true`, `verdict: null`, and
      `preview.candidate_written: false`.
- [x] No test or tool executed the fixture/candidate on the host.
- [x] Error string, input boundary and exit codes were not changed.
- [x] The new fixture, if not yet published, is still treated as unavailable;
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

- [x] `feat(repair): add elf64 core + cave finder dry-run tools`
- [x] `feat(repair): add patch writer + self-check with manifest output`
- [x] `test(repair): add unit tests covering boundary, reversibility, determinism`
- [x] `docs(repair): add dry-run docs, guard ABI and preflight notes`

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
