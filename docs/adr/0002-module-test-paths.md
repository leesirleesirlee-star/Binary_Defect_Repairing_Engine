# ADR 0002: test directories belong to the module they test

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** M1 (lead); M2, M3, M4, M5 informed
- **Supersedes:** none

## Context

`modules.json` is the single source of truth for ownership, and `scripts/check_modules.py`
fails any PR whose changed files do not match the declared module. `pipeline/ai/`
belongs to the `ai` module and `pipeline/audit/` to `audit`, but the registry lists
no `tests/ai/` or `tests/audit/` path.

The catch-all `tests/` prefix in the `infra` module therefore claims those test
directories, so M4's #34 (prompt builder + provider transport) fails `ci / modules`
for a single-file reason: `tests/ai/test_prompt.py` resolves to `infra`. The same
will happen to `tests/audit/` in #9. M4 cannot add or change its own tests without
an M1-owned infra PR, which inverts ownership for the least significant files.

## Decision

1. A module's tests live in `tests/<module-id>/` and belong to that module, exactly
   like the module's `pipeline/<id>/` code.
2. The registry gains the two missing paths now: `tests/ai/` for `ai`,
   `tests/audit/` for `audit`. `tests/analysis/`, `tests/repair/`, `tests/app/`,
   `tests/fixture/` and `tests/verify/` already follow this rule.
3. When a module later gains a `tests/<id>/` directory, the module owner adds the
   path to `modules.json`; the registry edit is still M1's, but it is bookkeeping of
   an existing boundary, not a new boundary decision.
4. `infra` keeps the `tests/` catch-all for cross-cutting tests only.

## Consequences

- `#34` and `#9` can carry their own tests under `module:ai` / `module:audit`.
- `sync` reviews: the module owner reviews their tests; M1 still reviews the
  registry change itself.
- CODEOWNERS gains `/tests/ai/` and `/tests/audit/` under the M4 block.
- The ownership docs (`docs/plan/01-team-ownership.md`, `docs/plan/04-module-matching.md`)
  list the new paths.

## Alternatives rejected

- **Label #34 `module:integration`:** hides a single-module PR behind the
  cross-module label and defeats the review routing it exists for.
- **Keep tests under `infra`:** every M4 test change would need an M1 PR, and the
  ownership matrix would say M4 owns code it cannot test.
