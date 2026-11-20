# GitHub workflow and repository control

**Status:** proposal, 2026-11-20
**Repository:** <https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine> (public, empty, default branch `main`)
**Archive:** <https://github.com/leesirleesirlee-star/Binary_Repair> (v1.2.2, read-only reference)

## 1. What "controlled" means here

Five people can work in parallel only if the repository, not chat, is the source
of truth. The controls are deliberately small:

- `main` is protected; nobody pushes to it directly.
- One issue = one branch = one owner = one PR.
- `CODEOWNERS` routes every path to exactly one reviewer/owner.
- CI runs on every PR and never executes a binary.
- A project board shows the one thing each person is doing now.
- Gate tags and release tags are created only by M1 after a recorded review.

## 2. Day 0 bootstrap

The repository is empty, so the first commit defines the rules. Do this in order;
protection is enabled only after `CODEOWNERS` exists on `main`.

### 2.1 Clone and first commit (M1)

```bash
git clone https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine.git
cd Binary_Defect_Repairing_Engine
git checkout -b main

# M1 writes the skeleton:
#   README.md AGENTS.md CONTRIBUTING.md SECURITY.md LICENSE .gitignore .editorconfig
#   pyproject.toml
#   .github/CODEOWNERS .github/PULL_REQUEST_TEMPLATE.md .github/ISSUE_TEMPLATE/*
#   .github/workflows/ci.yml
#   docs/README.md docs/plan/* docs/adr/0000-template.md docs/interfaces/README.md
#   schemas/README.md
#   app/README.md fixtures/README.md guest/README.md pipeline/README.md
#   tests/README.md scripts/README.md

git add README.md AGENTS.md CONTRIBUTING.md SECURITY.md LICENSE .gitignore .editorconfig pyproject.toml .github docs schemas app fixtures guest pipeline tests scripts
git commit -m "chore: initial MVP2 skeleton and repository rules"
git push -u origin main
```

Do not commit `.env`, `var/`, `__pycache__`, `.venv`, model keys, binaries other
than the declared fixture, or client material. `.gitignore` must be in the first
commit.

### 2.2 Repository settings (M1, GitHub UI)

| Setting | Value |
|---|---|
| Description | `AI-assisted binary defect repair with independently verified evidence` |
| Topics | `binary-analysis`, `vulnerability-repair`, `ai`, `x86-64`, `elf`, `fastapi` |
| Default branch | `main` |
| License | MIT (add `LICENSE` in the first commit) |
| Features | Issues on, Projects on, Wiki off, Discussions off |
| Merge button | Allow squash merge only; disable merge commit and rebase merge |
| Auto-delete head branches | On |
| Secrets | None in CI for MVP2; the provider key stays in the host process |

### 2.3 Collaborators (M1)

Invite the five accounts with **Write** permission:

```text
@chenfanaichifan
@huajinyao
@hxw64
@lyz200807
@leesirleesirlee-star
```

The owner account keeps Admin. Do not give Admin to every member; M1 is the
release manager. If a sixth account is the instructor, give Read-only.

### 2.4 Branch protection for `main` (M1)

Use **Settings > Rules > Rulesets > New branch ruleset** (public repository, no
paid plan needed):

- Target: `main`.
- Enforce for administrators: on.
- Require a pull request before merging:
  - required approvals: **1**;
  - dismiss stale approvals when new commits are pushed: on;
  - require review from Code Owners: on;
  - require conversation resolution: on.
- Require status checks to pass: `ci / test` and `ci / modules` (the job names in
  `.github/workflows/ci.yml`), and require the branch to be up to date before
  merging.
- Block force pushes: on.
- Restrict deletions: on.
- Allow only squash merge at the repository level.

If rulesets are unavailable, use the classic branch protection rule with the same
values. Screenshot the settings page into `docs/plan/evidence/` so the team can
prove the control exists.

### 2.5 Labels (M1)

Create these labels before opening the first issues. Colors are suggestions.

| Label | Color | Use |
|---|---|---|
| `module:contract` | `#5319e7` | schemas, contract, interfaces |
| `module:infra` | `#6a737d` | repo, CI, plans, archive, scripts |
| `module:fixture` | `#0e8a16` | fixture, PoC, corpus |
| `module:guest` | `#006b75` | isolated execution and observation |
| `module:verify` | `#1d76db` | deterministic checks and verdict |
| `module:analysis` | `#0052cc` | disassembly view and finding |
| `module:ai` | `#5319e7` | provider transport and prompt |
| `module:audit` | `#7b61ff` | audit runner, rubric, report |
| `module:repair` | `#b60205` | patch, candidate, edit manifest |
| `module:gui` | `#fbca04` | screens, API, rendering |
| `module:integration` | `#8a2be2` | M1-only cross-module gate PRs |
| `type:feat` | `#a2eeef` | new behavior |
| `type:fix` | `#d73a4a` | defect |
| `type:docs` | `#0075ca` | documentation |
| `type:test` | `#bfd4f2` | tests only |
| `type:decision` | `#c5def5` | ADR / scope decision |
| `priority:P0` | `#b60205` | blocks the current gate |
| `priority:P1` | `#d93f0b` | needed this phase |
| `priority:P2` | `#fbca04` | later |
| `status:blocked` | `#000000` | waiting on a named artifact |
| `gate:g0` ... `gate:g4` | `#ededed` | which gate the issue serves |

### 2.6 Milestones (M1)

| Milestone | Due | Exit |
|---|---|---|
| G0 Bootstrap | 2026-11-24 | protected repo, CI green, schemas v0, plan approved |
| G1 Fixture + PoC | 2026-12-01 | fixture frozen, original observations recorded |
| G2 AI Audit | 2026-12-08 | 3 plans, rubric, signed audit decision |
| G3 Repair + Verify | 2026-12-17 | candidate verified, evidence bundle |
| G4 GUI + Delivery | 2026-12-24 | four-screen demo, screenshots, `v0.1.0` |

### 2.7 Project board (M1)

Create one project, `MVP2`, with:

- **Views:** Board (Backlog, Ready, In progress, In review, Blocked, Done),
  Table (all fields), Roadmap (by milestone).
- **Fields:** Seat (M1-M5), Module
  (contract/infra/fixture/guest/verify/analysis/ai/audit/repair/gui),
  Gate (G0-G4), Priority (P0/P1/P2), Depends on (text or issue link).
- **WIP limit:** one `In progress` issue per person. A second issue may be
  `Ready` but not started.
- **Rule:** every PR links its issue; closing the issue moves the card to Done.

## 3. Branch model

```text
main                         protected, always green, release-ready
  ├─ feat/<module>/<issue>-<slug>   one feature or task
  ├─ fix/<area>/<issue>-<slug>      one defect
  ├─ docs/<issue>-<slug>            documentation only
  └─ chore/<area>/<slug>            tooling, CI, deps
```

Examples: `feat/fixture/12-poc-corpus`, `feat/analysis/15-disassembly-view`,
`feat/repair/21-guard-stub`, `feat/gui/24-analysis-screen`.

Rules:

- Branch from the current `main`; rebase before opening the PR.
- One branch serves one issue; do not bundle unrelated modules.
- Delete the branch after merge (auto-delete is on).
- Never force-push a branch that has an open PR with reviews; add a new commit.
- No long-lived environment branches. Tags, not branches, mark gates.

## 4. Issue model

Every task starts as an issue. A task without an issue is not started.

### Task issue template

```text
Title: [module] short imperative goal

Goal
  What user-visible or evidence-visible outcome does this produce?

Owner / module / gate
  Seat: M?
  Module: contract | infra | fixture | guest | verify | analysis | ai | audit | repair | gui
  Gate: G0 | G1 | G2 | G3 | G4

Inputs
  Artifact IDs and hashes this task consumes (H1, H2, ...).

Acceptance criteria
  - [ ] observable check 1
  - [ ] observable check 2
  - [ ] evidence artifact committed or attached

Out of scope
  What this task deliberately does not do.

Dependencies
  Blocked by #... / blocks #...

Definition of done
  - [ ] PR merged with owner approval
  - [ ] tests pass in CI (including the module scope check)
  - [ ] docs updated in the owner's docs folder
  - [ ] no file outside the owner's paths changed
```

### Bug issue template

```text
Repro (command + input)
Expected
Actual (exit code, stdout, stderr, hashes)
Environment (OS, Python, tool versions)
Suspected area
Evidence (log excerpt, artifact link)
```

### Decision issue / ADR template

```text
Context
Options (at least two, with tradeoffs)
Decision
Consequences (positive, negative, follow-ups)
Affected artifacts and owners
Status: proposed | accepted | superseded
```

ADRs live in `docs/adr/NNNN-short-title.md` and are merged like code. A decision
that changes the contract, the corpus, the result vocabulary, the repair route or
the repository layout requires an ADR.

## 5. PR model

### Before opening

- [ ] The branch is rebased on `main`.
- [ ] CI passes locally: `ruff check .` and `pytest -q -m "not guest"`.
- [ ] `git diff --stat` touches only the owner's paths.
- [ ] The PR is under 400 changed lines, or the description explains why not.
- [ ] The linked issue has acceptance criteria.

### PR body

```text
## Summary
What changed and why (2-4 sentences).

## Issue / module / gate
Closes #12. Module label: `module:fixture`. Gate: G1.

## Evidence
Commands run and observed output. For evidence work: artifact path + SHA-256.

## Checks
- [ ] pytest -q -m "not guest"
- [ ] ruff check .
- [ ] python scripts/check_modules.py --base origin/main
- [ ] no secrets / client data / private logs
- [ ] no file outside the declared module
- [ ] docs updated in my module

## Acceptance impact
Which criteria, observations or verdict state can change? If none, say "none".

## Rollback
How to revert this change safely.
```

### Review rules

- The CODEOWNER of every changed path must approve. For a PR touching two modules,
  both owners approve.
- M1 approves any change under `schemas/`, `docs/interfaces/`, `.github/`, or the
  root files, and any PR that changes a gate artifact.
- Review SLA: one working day. If the reviewer is unavailable, M1 substitutes and
  records it in the PR.
- Reviewers check evidence, not style alone: commands run, hashes, failing cases,
  and the "no success without verdict" rule.
- Authors merge after approval and green CI (squash). M1 merges gate PRs.
- Never approve your own PR. Never merge with a failing required check.

### PR size guide

| Size | Action |
|---|---|
| < 200 lines | normal |
| 200-400 lines | normal, explain in the summary |
| > 400 lines | split by area or by test/implementation, unless it is a generated fixture or a docs import approved by M1 |

## 6. CI

CI is a **host-side static check**. It must never execute the fixture, a candidate
or model-generated code. Guest tests are marked `@pytest.mark.guest` and excluded.

```yaml
name: ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt
      - name: Lint
        run: ruff check .
      - name: Test (host only)
        run: python -m pytest -q -m "not guest"

  modules:
    name: modules
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Fetch base branch
        run: git fetch --no-tags origin ${{ github.base_ref }}
      - name: Check module scope
        run: |
          python scripts/check_modules.py \
            --base FETCH_HEAD \
            --labels "${{ join(github.event.pull_request.labels.*.name, ',') }}"
```

Notes:

- Both jobs must pass; branch protection requires the checks `ci / test` and
  `ci / modules`.
- Every PR needs exactly one `module:<id>` label. The `modules` job fails if the
  label is missing, duplicated, or a changed file falls outside that module.
- Docs-only PRs still run CI; it is fast enough. Do not add path filters until the
  suite is slow.
- `requirements.txt` pins the host/CI dependencies; `pyproject.toml` holds the
  ruff and pytest configuration.
- No `DEEPSEEK_API_KEY` in GitHub. The AI audit runs on a host with the key and
  commits only the redacted report, prompt hash and response hash.
- Browser e2e is local, not CI, until a stable headless runner is agreed.

## 7. Releases and tags

| Tag | When | Content |
|---|---|---|
| `g0-bootstrap` | G0 | skeleton, protected repo, schemas v0 |
| `fixture-v1` | G1 | fixture, PoC, corpus, original observations |
| `audit-v1` | G2 | disassembly, 3 plans, audit report |
| `candidate-v1` | G3 | candidate ELF, edit manifest, verdict |
| `v0.1.0` | G4 | demo, docs, evidence bundle |

Rules:

- Only M1 creates or moves tags. A tag is annotated and points to a merged
  commit on `main`.
- Never move an existing tag; create a new version.
- Release notes list the tag's evidence hashes and the limitations. Do not call a
  release "secure" or "production-ready".

## 8. Day-to-day rhythm

| When | What | Who |
|---|---|---|
| Monday 30 min | Pick one issue per seat; update board; confirm gates | all |
| Daily async | PR/issue updates only; no status messages in chat | all |
| Wednesday 15 min | Blockers only; name the missing artifact | all |
| Friday 30 min | Demo the week's artifact; merge gate PRs; record results | all |
| Before a gate | M1 re-runs the gate command and writes the dated record | M1 |

The repository is the message bus. A chat message may say "PR is up"; it may not
be the only place a decision or an evidence claim exists.

## 9. Conflict prevention checklist

Before starting work:

- [ ] The issue has one owner and one area label.
- [ ] The files I will touch are in my ownership matrix.
- [ ] No open PR touches the same files; if one does, I wait or split.
- [ ] I branched from today's `main`.
- [ ] My change is under 400 lines.

Before merging:

- [ ] The PR touches only my paths (plus a schema change approved by M1).
- [ ] CI is green and the branch is up to date.
- [ ] The CODEOWNER approved.
- [ ] No generated artifact was hand-edited.
- [ ] The issue's acceptance criteria are checked.

## 10. Security and data rules

- No API key, token, `.env`, private log or client binary in the repository.
- The provider key lives only in the host process environment; it is never sent
  to the browser, the guest, CI logs or the audit report.
- The guest receives the fixture, the contract and the candidate; it never
  receives the key or the source directory.
- Uploaded binaries are not accepted in MVP2; the fixture is built in.
- The audit report may include model output, but not the raw key or account data.
- Enable GitHub secret scanning and Dependabot alerts after the first commit.
- If a secret is committed, rotate it first, then rewrite history with M1; do not
  just delete the file in a later commit.

## 11. Ready-to-paste CODEOWNERS

Replace the handles only if the confirmed mapping in `01-team-ownership.md`
changes. The file must exist on `main` before "Require review from Code Owners" is
enabled.

The second handle on an M1-owned path is a **review backup**, not an edit
permission: it lets an M1-authored infra PR be approved by M2 without disabling
the code-owner rule. Edit ownership stays with M1 as listed in the matrix.

```text
# Default: M1 owns integration; M2 is the review backup for M1-authored PRs.
*                                   @leesirleesirlee-star @huajinyao

/.github/                           @leesirleesirlee-star @huajinyao
/README.md                          @leesirleesirlee-star @huajinyao
/AGENTS.md                          @leesirleesirlee-star @huajinyao
/CONTRIBUTING.md                    @leesirleesirlee-star @huajinyao
/SECURITY.md                        @leesirleesirlee-star @huajinyao
/pyproject.toml                     @leesirleesirlee-star @huajinyao
/schemas/                           @leesirleesirlee-star @huajinyao
/scripts/                           @leesirleesirlee-star @huajinyao
/docs/plan/                         @leesirleesirlee-star @huajinyao
/docs/adr/                          @leesirleesirlee-star @huajinyao
/docs/interfaces/                   @leesirleesirlee-star @huajinyao
/docs/README.md                     @leesirleesirlee-star @huajinyao

/app/                               @huajinyao
/tests/app/                         @huajinyao
/docs/gui/                          @huajinyao

/fixtures/                          @chenfanaichifan
/guest/                             @chenfanaichifan
/pipeline/verify/                   @chenfanaichifan
/tests/fixture/                     @chenfanaichifan
/docs/fixture/                      @chenfanaichifan

/pipeline/analyze/                  @hxw64
/pipeline/ai/                       @hxw64
/pipeline/audit/                    @hxw64
/prompts/                           @hxw64
/tests/analysis/                    @hxw64
/docs/analysis/                     @hxw64
/docs/audit/                        @hxw64

/pipeline/repair/                   @lyz200807
/tests/repair/                      @lyz200807
/docs/repair/                       @lyz200807
```

## 12. Weekly gate record

At each gate, M1 commits one record under `docs/adr/` or `docs/plan/records/`
with:

- gate name, date, commit SHA and tag;
- artifacts and SHA-256 values;
- the command that was run and its observed output;
- pass/fail per criterion, including `not_run`;
- who reviewed, and the same-person limitation;
- the next gate's decision.

A gate record is not a press release. It must be possible to re-run the commands
and get the same result, or the record says why not.
