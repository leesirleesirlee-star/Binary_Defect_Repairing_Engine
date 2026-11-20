# GitHub project control and precise module matching

**Status:** proposal, 2026-11-20
**Used by:** `.github/CODEOWNERS`, `.github/workflows/ci.yml`, `modules.json`, `scripts/check_modules.py`, `docs/plan/02-github-workflow.md`

## 1. Problem

Five people in one repository will collide unless "who owns what" is machine
checkable, not a paragraph in a document. GitHub already has two useful pieces:

- **CODEOWNERS** decides *who must review* a changed path.
- **Branch protection** decides *when a PR may merge*.

Neither decides *whether a PR is allowed to touch those files at all*. A PR can
change three modules and still be reviewed by one person. Labels are manual and
drift. The result is the exact failure mode the team wants to avoid: someone
edits another seat's module, the review misses it, and the conflict lands on
`main`.

This document adds a third layer: a **module registry** and a **CI scope check**.

## 2. What a module is here

A module is a directory (or a small set of paths) that has:

- exactly one owning seat;
- one public interface (JSON artifact or Python function);
- one set of tests;
- one gate where its output is frozen.

A module is not a Python package for distribution. It is a **write-scope and
review unit**.

## 3. The ten modules

| ID | Title | Seat | Owner | Paths | Gate |
|---|---|---|---|---|---|
| `contract` | Contracts, schemas, interfaces | M1 | `@leesirleesirlee-star` | `schemas/`, `docs/interfaces/`, `docs/adr/`, `tests/contract/` | G0 |
| `infra` | Repository, CI, plans, archive | M1 | `@leesirleesirlee-star` | `.github/`, `scripts/`, `docs/` (catch-all), `tests/` (catch-all), root files, `modules.json`, `requirements.txt`, `pyproject.toml` | G0 |
| `fixture` | Vulnerable sample, PoC, corpus | M3 | `@chenfanaichifan` | `fixtures/`, `tests/fixture/`, `docs/fixture/` | G1 |
| `guest` | Isolated execution and observation | M3 | `@chenfanaichifan` | `guest/` | G1 |
| `verify` | Deterministic checks and verdict | M3 | `@chenfanaichifan` | `pipeline/verify/`, `tests/verify/` | G3 |
| `analysis` | ELF facts and disassembly view | M4 | `@hxw64` | `pipeline/analyze/`, `tests/analysis/`, `docs/analysis/` | G2 |
| `ai` | Provider transport and prompt | M4 | `@hxw64` | `pipeline/ai/`, `prompts/` | G2 |
| `audit` | Audit runner, rubric, report | M4 | `@hxw64` | `pipeline/audit/`, `docs/audit/` | G2 |
| `repair` | Cave finder, patch, manifest | M5 | `@lyz200807` | `pipeline/repair/`, `tests/repair/`, `docs/repair/` | G3 |
| `gui` | FastAPI app, templates, rendering | M2 | `@huajinyao` | `app/`, `tests/app/`, `docs/gui/` | G4 |

`infra` is deliberately broad: it owns the root files and the catch-all
`docs/` and `tests/`. Specific modules declare longer path prefixes, so the
longest-prefix rule sends `docs/audit/x.md` to `audit`, not `infra`.

## 4. Single source of truth: `modules.json`

`modules.json` is the machine-readable registry. Every other artifact is
checked against it:

```json
{
  "schema_version": 1,
  "modules": [
    {
      "id": "audit",
      "title": "Audit runner, rubric, report",
      "seat": "M4",
      "owner": "@hxw64",
      "paths": ["pipeline/audit/", "docs/audit/"],
      "may_depend_on": ["contract", "analysis", "ai"],
      "forbidden_paths": ["fixtures/"],
      "interfaces": ["FixPlanV1", "AuditReportV1"],
      "gate": "G2",
      "notes": "The audit may read the disassembly view and the contract, never the fixture build directory."
    }
  ]
}
```

Rules for the registry:

- `id` is unique and matches the `module:<id>` label.
- `seat` is one of `M1`..`M5`; `owner` is the GitHub handle.
- `paths` are workspace-relative prefixes ending in `/`, or exact file paths.
- `may_depend_on` is the allowed direction of imports/reads.
- `forbidden_paths` are paths the module must never read, even transitively.
- `interfaces` are the frozen artifacts it produces or consumes.
- `gate` is the first gate where the module's output must be frozen.

`modules.json` itself belongs to `infra`; only M1 edits it, with an ADR.

## 5. Matching algorithm

`scripts/check_modules.py` classifies every changed file:

1. Normalize `\` to `/`, strip a leading `./`.
2. Ignore `var/`, `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/`.
3. If the file exactly equals an explicit module path, that module wins.
4. Otherwise, among prefixes ending in `/`, the **longest** matching prefix wins.
5. If two modules claim the same path length, the registry is invalid; fail.
6. If no module matches, the file is **unowned**; fail.

The check has two modes:

```bash
# Ownership only: every changed file belongs to some module.
python scripts/check_modules.py --base origin/main

# Scope + ownership: all files belong to the declared module label.
python scripts/check_modules.py --base origin/main --labels "module:repair,type:feat"
```

`--labels` requires exactly one `module:<id>` label. `module:integration` is the
only exception: it allows cross-module changes and is reserved for M1 gate PRs
(the CODEOWNERS default still requires M1 or M2 review).

## 6. Three enforcement layers

| Layer | Artifact | What it enforces | What it does not |
|---|---|---|---|
| Review routing | `.github/CODEOWNERS` | the owner of each path must approve | does not limit the PR's scope |
| Merge gate | `main` ruleset | PR, 1 approval, code owner, CI, up to date | does not know the module label |
| Scope gate | `modules.json` + `check_modules.py` + `module:*` label | changed files stay inside the declared module | does not judge code quality |

The layers are complementary. A PR that edits `pipeline/verify/` and
`pipeline/repair/` is caught by the scope gate; a PR that edits only
`pipeline/repair/` is routed to M5 by CODEOWNERS; a PR that tries to merge
without approval is blocked by the ruleset.

## 7. Dependency direction

The module graph is a DAG. Reads/imports may only go left to right:

```text
contract ──> fixture ──> guest ──> verify ──> gui
    │            │                      ^
    │            └──> analysis ──> ai ──┘
    │                     │         │
    │                     └──> audit ┘
    │                              │
    └──────────────────────────> repair
```

Allowed reads (not exhaustive):

- `analysis` reads the ELF artifact and the contract; never `fixtures/**/build/`.
- `ai` reads the contract and the disassembly view; never the fixture binary or
  source.
- `audit` reads `analysis` output, `ai` output and the contract; never the
  verifier's hidden corpus.
- `repair` reads the approved plan, the contract and the ELF; never
  `pipeline/verify/` or the corpus.
- `verify` reads the candidate, the original, the corpus and the contract; never
  the AI plan or the repair source.
- `gui` reads persisted JSON; it does not import `pipeline.verify` or compute a
  verdict.

Forbidden directions (also in `forbidden_paths`):

| Module | Must not read/import |
|---|---|
| `analysis` | `fixtures/**/build/`, `pipeline/ai/`, `pipeline/repair/` |
| `ai` | `fixtures/`, `pipeline/verify/`, `app/` |
| `audit` | `pipeline/verify/`, `fixtures/**/build/` |
| `repair` | `pipeline/verify/`, `fixtures/**/cases/`, `app/` |
| `verify` | `pipeline/ai/`, `pipeline/audit/`, `pipeline/repair/` |
| `gui` | `pipeline/verify/`, `pipeline/repair/`, `pipeline/ai/` |

These are review rules for MVP2. A future CI job can parse imports to enforce
them mechanically; the path ownership check is the first layer.

## 8. PR flow with precise matching

1. Pick an issue with exactly one module label, for example `module:repair`.
2. Branch: `feat/repair/21-guard-stub`.
3. Change only files under the module's paths.
4. Add the same `module:repair` label to the PR (the template asks for it).
5. CI runs `check_modules.py`; if a file falls outside `repair`, the check fails
   with the offending path and its actual module.
6. CODEOWNERS requests M5; M1 approves gate PRs; squash merge.

A docs-only PR uses `module:infra` or the documentation owner's module. A PR that
must touch two modules is split, unless M1 labels it `module:integration` and
explains why in the PR body.

## 9. GitHub project setup for modules

- **Labels:** `module:contract`, `module:infra`, `module:fixture`, `module:guest`,
  `module:verify`, `module:analysis`, `module:ai`, `module:audit`,
  `module:repair`, `module:gui`, `module:integration`.
- **Project field:** `Module` single-select with the same values. Set it from the
  issue/PR label; every card must have one.
- **Board:** the `Module` field is the swimlane or the filter. A weekly view
  `Module = repair` answers "what is M5 doing" without asking.
- **Milestones:** G0-G4; a module's gate is in `modules.json` and on the card.

## 10. Why not just CODEOWNERS

CODEOWNERS answers "who reviews this file". It does not answer:

- Did the PR stay in the module it claims to work on?
- Did a docs PR silently edit a test fixture?
- Did the repair seat read the verifier to make a test pass?

The registry plus the scope check answers those. It is also the data source for
the board, the labels and the onboarding document, so the team maintains one
table instead of five.

## 11. Failure messages and fixes

| Message | Meaning | Fix |
|---|---|---|
| `unowned: src/foo.py` | no module claims the path | add it to a module in `modules.json` (ADR + M1) or delete it |
| `outside module repair: app/main.py -> gui` | PR label and changed file disagree | move the file back, split the PR, or ask M1 for `module:integration` |
| `missing module label` | PR has zero `module:*` labels | add exactly one |
| `multiple module labels` | PR has two or more | keep the one that matches the changed paths |
| `ambiguous path: docs/x` | two modules claim the same prefix length | fix `modules.json`; this is a registry bug |
| `git diff failed` | base ref not fetched | run `git fetch origin main` |

## 12. First-run checklist

- [ ] `modules.json` committed and valid JSON.
- [ ] `scripts/check_modules.py` exits 0 on a clean tree and 1 on a file outside
      the declared module.
- [ ] `tests/test_module_map.py` passes.
- [ ] `.github/CODEOWNERS` paths match `modules.json`.
- [ ] The ten `module:*` labels exist.
- [ ] The project has a `Module` field.
- [ ] The PR template asks for the module label.
- [ ] `main` ruleset requires `ci / test` and `ci / modules`.
- [ ] The first PR (M1 skeleton) uses `module:infra`.
