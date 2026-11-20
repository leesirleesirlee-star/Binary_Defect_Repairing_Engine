# Contributing

## Before you start

1. Read [`START-HERE.md`](START-HERE.md) and [`AGENTS.md`](AGENTS.md).
2. Find your module in [`modules.json`](modules.json).
3. Pick an issue that has exactly one `module:<id>` label.

## Branch and PR

- Branch from the current `main`: `feat/<module>/<issue>-<slug>`.
- One issue, one module, one owner, one PR. Keep the PR under 400 changed lines.
- Add the same `module:<id>` label to the PR. CI checks that every changed file
  belongs to that module.
- Do not edit files outside your module. If the change needs another module,
  split the PR or open an issue.
- Fill in the PR template, including the commands you ran and their observed
  output.

## Checks

```bash
python -m pip install -r requirements.txt
ruff check .
python -m pytest -q -m "not guest"
python scripts/check_modules.py --base origin/main
```

`guest` tests run only in the disposable guest; report them as `not_run` when
they did not run. A green CI is not a repair verdict.

## Review

- The module owner reviews; M1 reviews gate PRs and all shared files.
- One approval plus green `ci / test` and `ci / modules` is required.
- Squash merge only; delete the branch after merge.
- Never approve your own PR and never merge with a failing required check.

## Evidence

- A claim needs a commit, a command, an observed output and a hash.
- Do not weaken a test, contract, corpus, gate or rubric to get green.
- `not_run` and `unverified` are valid results; a missing check is not a pass.

## Secrets and data

- No API keys, `.env`, private logs, client binaries or confidential material.
- The provider key stays in one host process and never enters the repository,
  the guest, CI logs or an audit report.
