# GitHub setup runbook (M1, run once)

**Status:** execute after the team approves the plan. This is the operational
checklist; the rules are in [`02-github-workflow.md`](02-github-workflow.md) and
the module mechanism is in [`04-module-matching.md`](04-module-matching.md).

Repository: <https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine>

## 0. Push the skeleton

The local folder already contains the first commit
(`chore: initial MVP2 skeleton and repository rules`). Push it:

```bash
cd Binary_Defect_Repairing_Engine
git remote -v
git push -u origin main
```

If authentication fails, use GitHub Desktop or a personal access token in the
credential helper. Never commit the token, `.env` or a key.

After the push, open the repository and confirm the 62 files, `CODEOWNERS`,
`modules.json`, `ci.yml` and the plan docs are present.

## 1. Repository settings

| Setting | Value |
|---|---|
| Description | `AI-assisted binary defect repair with independently verified evidence` |
| Topics | `binary-analysis`, `vulnerability-repair`, `ai`, `x86-64`, `elf`, `fastapi` |
| Default branch | `main` |
| License | MIT (already in `LICENSE`) |
| Features | Issues on, Projects on, Wiki off, Discussions off |
| Merge | Allow squash merge only; disable merge commit and rebase merge |
| Auto-delete head branches | On |
| Secrets | None for MVP2 |

## 2. Collaborators

Invite the five accounts with **Write** permission; keep Admin on the owner
account only:

```text
@chenfanaichifan
@huajinyao
@hxw64
@lyz200807
@leesirleesirlee-star
```

Confirm the seat mapping before you enable code-owner review. The provisional map
is in `docs/plan/01-team-ownership.md` and `modules.json`.

## 3. Labels

Create one `module:*` label per module plus the type, priority and status labels.
With GitHub CLI:

```bash
gh label create "module:contract"    --color 5319e7 --force
gh label create "module:infra"       --color 6a737d --force
gh label create "module:fixture"     --color 0e8a16 --force
gh label create "module:guest"       --color 006b75 --force
gh label create "module:verify"      --color 1d76db --force
gh label create "module:analysis"    --color 0052cc --force
gh label create "module:ai"          --color 5319e7 --force
gh label create "module:audit"       --color 7b61ff --force
gh label create "module:repair"      --color b60205 --force
gh label create "module:gui"         --color fbca04 --force
gh label create "module:integration" --color 8a2be2 --force

gh label create "type:feat"     --color a2eeef --force
gh label create "type:fix"      --color d73a4a --force
gh label create "type:docs"     --color 0075ca --force
gh label create "type:test"     --color bfd4f2 --force
gh label create "type:decision" --color c5def5 --force
gh label create "priority:P0"   --color b60205 --force
gh label create "priority:P1"   --color d93f0b --force
gh label create "priority:P2"   --color fbca04 --force
gh label create "status:blocked" --color 000000 --force
```

If `gh` is unavailable, create the same names in **Issues > Labels**. The CI
module check only recognises the `module:<id>` labels.

## 4. Milestones

Create G0-G4 with the dates in `docs/plan/00-mvp2-roadmap.md`:

```bash
gh api repos/leesirleesirlee-star/Binary_Defect_Repairing_Engine/milestones \
  -f title="G0 Bootstrap" -f due_on="2026-11-24T00:00:00Z"
# repeat for G1 2026-12-01, G2 2026-12-08, G3 2026-12-17, G4 2026-12-24
```

## 5. Protect `main`

Do this **after** the first push, because the ruleset needs `CODEOWNERS` and the
CI checks. The checks appear only after the first PR runs.

**Settings > Rules > Rulesets > New branch ruleset:**

- Target: `main`.
- Enforce for administrators: on.
- Require a pull request: 1 approval, dismiss stale approvals, code-owner review,
  conversation resolution.
- Require status checks: `ci / test` and `ci / modules`; require the branch to be
  up to date.
- Block force pushes; restrict deletions.
- Allow squash merge only at the repository level.

Screenshot the ruleset into `docs/plan/evidence/` (create the folder in the same
PR as the screenshot) so the control is auditable.

## 6. Project board

Create one project, `MVP2`:

- Views: Board (Backlog / Ready / In progress / In review / Blocked / Done),
  Table, Roadmap by milestone.
- Fields: Seat (M1-M5), Module (the ten module ids), Gate (G0-G4),
  Priority (P0/P1/P2), Depends on.
- WIP limit: one `In progress` card per person.
- Rule: every issue and PR carries exactly one `module:<id>` label; the card
  shows the same module.

## 7. First issues

Create these as a starter set. Each has one module, one seat and one gate.

| # | Title | Module | Seat | Gate |
|---|---|---|---|---|
| 1 | Protect `main` and enable CI | `infra` | M1 | G0 |
| 2 | Write `ContractV1` and `FixPlanV1` v0 | `contract` | M1 | G0 |
| 3 | Build the four-screen static prototype | `gui` | M2 | G0 |
| 4 | Write the 32-byte C fixture and build recipe | `fixture` | M3 | G1 |
| 5 | Write the PoC and valid/invalid corpus | `fixture` | M3 | G1 |
| 6 | Build `run_cases.py` and capture original observations | `guest` | M3 | G1 |
| 7 | Build the disassembly view and source-separation test | `analysis` | M4 | G2 |
| 8 | Write the prompt and the three-run audit harness | `ai` + `audit` | M4 | G2 |
| 9 | Build the cave finder and patch writer dry-run | `repair` | M5 | G3 |
| 10 | Implement V0-V4 verifier and verdict writer | `verify` | M3 | G3 |
| 11 | Wire the four screens to JSON and add honesty tests | `gui` | M2 | G4 |

Issue 8 touches two modules; split it into `ai` (prompt + transport) and `audit`
(three-run report) before starting. Do not use `module:integration` for routine
work.

## 8. Prove the module check works

Before trusting the ruleset, run one negative test:

1. Create a branch `chore/infra/1-prove-module-check`.
2. Change one line in `app/README.md` (module `gui`) and open a PR labelled
   `module:infra`.
3. The `ci / modules` job must fail with:
   `outside module infra: app/README.md -> gui`.
4. Change the label to `module:gui`; the job must pass (the `test` job still
   runs).
5. Close the PR without merging, or merge it only if the change is real.

This is the only way to know the control is active rather than assumed.

## 9. Module matching troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ci / modules` says `exactly one module:<id> label is required` | PR has no `module:*` label (or two) | add exactly one |
| `multiple module labels` | PR has two | keep the one that matches the files |
| `outside module X: path -> Y` | file belongs to module Y | move the change to a Y PR, or ask M1 for `module:integration` |
| `unowned: path` | no module claims the path | add it to `modules.json` with an ADR, or delete it |
| `git diff failed` | base ref not fetched | run `git fetch origin main` |
| CODEOWNERS does not request review | file added after the last CODEOWNERS match | confirm the pattern in `modules.json` and `.github/CODEOWNERS` match |

## 10. Weekly rhythm

| When | What |
|---|---|
| Monday 30 min | Each seat picks one issue; update the board; confirm the gate |
| Wednesday 15 min | Blockers only; name the missing artifact |
| Friday 30 min | Demo the week's artifact; M1 merges gate PRs and records the result |
| Before a gate | M1 re-runs the gate command and writes the dated record |

## 11. Do not

- Do not push directly to `main`.
- Do not approve your own PR or merge with a red required check.
- Do not add a `module:integration` label to routine work.
- Do not copy old v1.2.2 code or evidence into the new tree; use
  [`../MIGRATION.md`](../MIGRATION.md).
- Do not put a provider key in GitHub, the browser, the guest or a report.
- Do not run the fixture or a candidate on the host; use `guest/`.
