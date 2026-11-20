# START HERE — Binary Defect Repairing Engine (MVP2)

**Status:** planning complete locally; GitHub repository is still empty; no
application code has been written. First milestone is **G0: repository
bootstrap**.
**Target repository:** <https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine>
**Archive repository:** <https://github.com/leesirleesirlee-star/Binary_Repair> (v1.2.2, accepted work, read-only reference)
**Reference report:** 2026-11-19, "AI-Assisted Binary Vulnerability Repair: Project Workflow and Technical Assessment".

This file is the handoff for a person or an AI agent who opens this folder with
no history. Read it before changing anything.

---

## 0. If you are an AI coding agent

1. Read [`AGENTS.md`](AGENTS.md). It is binding.
2. Find your module in [`modules.json`](modules.json) and
   [`docs/plan/04-module-matching.md`](docs/plan/04-module-matching.md). Only
   write files inside your module.
3. Do not execute the fixture, a candidate ELF, or model-generated code on this
   host. Execution belongs to the disposable guest under `guest/`.
4. Do not read `fixtures/**/build/` from analysis, AI or audit code. The C source
   is build-only; a test enforces the boundary.
5. Run the checks before you claim anything:
   `python scripts/check_modules.py --base origin/main`,
   `ruff check .`, `python -m pytest -q -m "not guest"`.
6. Report `not_run` and `unverified` honestly. A missing check is never a pass.

---

## 1. What this project is

A local analyst tool that repairs **one known stack buffer overflow** in a
**Linux x86-64 ELF without original source**, and reports evidence of correctness
against a **human-reviewed contract** and a **frozen regression corpus**.

The flow is deliberately short:

```text
original ELF ──┐
PoC + output ──┼─> [1] contract + corpus (humans, frozen before AI)
defect text  ──┘             │
                             v
                    [2] disassembly (deterministic)
                             │
                    [3] AI repair plan (model)
                             │
                    [4] human plan review  <── G2 hard gate
                             │ approved
                    [5] binary patch (one route)
                             │
                    [6] guest runs original vs candidate on the corpus
                             │
                    [7] deterministic verdict
                             │
                    [8] conversation console: event timeline + export
```

The **verdict vocabulary** is fixed:

| State | Meaning |
|---|---|
| `verified_against_stated_criteria` | every required criterion passed on matching hashes; scope is the written contract only |
| `rejected` | a required criterion failed |
| `unverified` | a required check did not run, was inconclusive, or evidence does not bind |
| `unsupported` | outside the declared scope |
| `error` | a tool or provider failed before a verdict |
| `not_run` | one check did not execute; never a pass |

**What this is not:** not a general exploit detector, not a formal proof, not a
production security product, not a claim that the program is secure. The report's
test-oracle problem is the reason: removing one observed crash does not establish
that normal behavior survived.

---

## 2. The one decision that shapes everything

The previous project let the AI draft the contract, propose the repair and be
evaluated against that same contract. That is circular. MVP2 separates the three:

- **M1 + M3** write and freeze the contract and the corpus, independently of any
  model output.
- **M4** asks the model for a repair plan and runs the audit.
- **M5** implements the approved plan; **M3** verifies it.
- **M2** renders the evidence; it never computes a verdict.

If the audit shows the model can produce usable plans but correctness cannot be
established, the project invests in verification, not in a bigger model. If no
usable plan appears, the product becomes "AI-assisted analysis + a human-authored
patch" and the report says so. Do not hide either outcome.

---

## 3. Read in this order

| # | Document | Why read it |
|---|---|---|
| 1 | [`README.md`](README.md) | one-page project overview |
| 2 | [`AGENTS.md`](AGENTS.md) | binding rules for people and agents |
| 3 | [`docs/plan/00-mvp2-roadmap.md`](docs/plan/00-mvp2-roadmap.md) | scope, phases, gates, target tree |
| 4 | [`docs/plan/01-team-ownership.md`](docs/plan/01-team-ownership.md) | five seats, file ownership, interfaces, conflict rules |
| 5 | [`docs/plan/02-github-workflow.md`](docs/plan/02-github-workflow.md) | branch/PR/issue/project/CI/release rules |
| 6 | [`docs/plan/03-fixture-and-ai-audit-spec.md`](docs/plan/03-fixture-and-ai-audit-spec.md) | fixture, PoC, corpus, prompt, rubric, G2 decision |
| 7 | [`docs/plan/04-module-matching.md`](docs/plan/04-module-matching.md) | `modules.json`, CI scope check, exact module matching |
| 8 | [`docs/MIGRATION.md`](docs/MIGRATION.md) | which old docs/files to import, which to leave in the archive |
| 9 | [`modules.json`](modules.json) | the machine-readable module registry |

Do not start with the old repository. It is an archive of a larger, different
scope; copying it wholesale recreates the problem this folder exists to avoid.

---

## 4. What exists in this folder today

| Path | State | Owner |
|---|---|---|
| `START-HERE.md`, `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md` | written | M1 |
| `docs/plan/00`-`04` | written | M1 |
| `docs/MIGRATION.md`, `docs/README.md` | written | M1 |
| `modules.json`, `scripts/module_registry.py`, `scripts/check_modules.py` | written, self-tested | M1 |
| `.github/CODEOWNERS`, PR/issue templates, `workflows/ci.yml` | written | M1 |
| `tests/test_module_map.py`, `tests/conftest.py` | written | M1 |
| `app/`, `fixtures/`, `guest/`, `pipeline/`, `prompts/`, `schemas/`, `tests/*` | empty skeleton with README placeholders | each seat |

No Python package code, no fixture binary, no GUI implementation and no AI call
exists yet. That is intentional: G0 is the repository, not the product.

---

## 5. What is not here, and where to find it

| Missing item | Where it lives | Action |
|---|---|---|
| Full v1.2.2 product code | `leesirleesirlee-star/Binary_Repair` (archive) | do not copy; import only the pieces in `docs/MIGRATION.md` |
| Old Route A/B, workers, artifacts, plugins, knowledge, data | archive repository | reference only; not in MVP2 |
| Old handoffs and acceptance claims | archive `docs/development/`, `docs/status/`, `docs/acceptance/` | read as history, not as current evidence for MVP2 |
| GUI visual assets | archive `app/templates/`, `app/static/` | M2 imports and adapts; see `docs/MIGRATION.md` |
| AI transport client | archive `binaryrepair_ai/` | M4 adapts `client.py`, `errors.py`, `settings.py`; not the old schemas |
| Old CWE-121 fixture | archive `fixtures/public/` | reference; MVP2 builds a new 32-byte fixture |

The archive is **read-only**. Do not push to it, do not move its tags, do not
cite its accepted verdict as MVP2's verdict.

---

## 6. The five seats and the ten modules

| Seat | Modules | First deliverable |
|---|---|---|
| **M1** Lead / contracts / integration | `contract`, `infra` | protected repo, CI green, contract v0, module registry |
| **M2** GUI / thin API | `gui` | conversation console (v1.2.2 chat UI), S1–S6 against example JSON |
| **M3** Fixture / guest / verification | `fixture`, `guest`, `verify` | 32-byte C fixture, PoC, corpus, original observations |
| **M4** Analysis / AI audit | `analysis`, `ai`, `audit` | disassembly view, prompt, 3 audit runs |
| **M5** Repair | `repair` | cave finder and patch writer dry-run (no fixture fix before G2) |

The full owner, path, dependency and gate table is in
[`modules.json`](modules.json) and
[`docs/plan/01-team-ownership.md`](docs/plan/01-team-ownership.md).

**One owner per path.** If you need a change outside your module, open an issue;
do not edit it. `scripts/check_modules.py` fails a PR whose files do not match its
one `module:<id>` label.

---

## 7. The next ten days (G0 -> G1)

### G0 — bootstrap, target 2026-11-24

- [ ] M1 pushes the skeleton as the first commit (`module:infra`).
- [ ] M1 creates the `module:*` labels, milestones G0-G4 and the `MVP2` project.
- [ ] M1 enables the `main` ruleset: PR, 1 approval, code owner, `ci / test` and
      `ci / modules`, up to date, no force push, admins included.
- [ ] M1 confirms the five GitHub handles and the seat mapping.
- [ ] M1 writes `schemas/ContractV1.json` and `schemas/FixPlanV1.json` v0.
- [ ] M2, M3, M4, M5 each open one issue with one module label and a first task.
- [ ] All five read this file and `AGENTS.md`; the lead records acceptance.

### G1 — fixture, target 2026-12-01

- [ ] M3 writes `fixtures/stack-overflow-01/build/vuln.c` and `build.sh`.
- [ ] M3 builds `vuln.elf`, records flags/toolchain/hash in `manifest.json`.
- [ ] M1 freezes `contract.json` after M3 review.
- [ ] M3 writes `cases/{valid,invalid,poc}.json` and `guest/run_cases.py`.
- [ ] M3 runs the original: valid cases pass, PoC exits on `SIGSEGV`; stores
      `observations-original.json`.
- [ ] M1 tags `fixture-v1` and writes the gate record.
- [ ] M4 confirms the disassembly view can be built from the frozen ELF without
      reading the source.

Do not start the AI audit before G1. Do not start the repair before G2.

### G2 — AI audit, target 2026-12-08

- [ ] M4 builds `pipeline/analyze/` and `disassembly.json`.
- [ ] M4 drafts the prompt and `FixPlanV1`; M1 and M5 review the rubric.
- [ ] M4 runs 3 audits on the frozen fixture; writes `docs/audit/`.
- [ ] M1 + M5 score; M3 confirms the contract/corpus did not change.
- [ ] Decision: `proceed` / `iterate` / `change_scope`; M1 signs.
- [ ] Only after `proceed` does M5 apply a patch to the fixture.

### G3 — repair and verify

- [ ] M5 writes the candidate from the approved plan; every edit is in `EditManifestV1`.
- [ ] M3 runs original vs candidate on the frozen corpus in the guest; `observations-candidate.json`.
- [ ] M3's deterministic verifier writes `verdict.json` with the six-word vocabulary.
- [ ] V0-V4 pass on matching hashes; an independent re-run reproduces the candidate.

### G4 — conversation console (delivery)

- [ ] `/welcome` → `/ui/chat/` → `/ui/` open without the Jinja legacy.
- [ ] intake attaches the binary, normal inputs and the crash input; the corpus card matches the frozen `cases.json`.
- [ ] approval binds contract + corpus + binary digests; Start is blocked until approved.
- [ ] Start spawns `python -m scripts.run_task --task <id>`; the SSE timeline renders real journal events.
- [ ] three audit runs, rubric and `proceed / iterate / change_scope` render from the persisted audit JSON.
- [ ] verdict card renders only the six-word vocabulary; `not_run` verbatim; downloads resolve.
- [ ] no `pipeline.*` import in `app/`; honesty tests green; headless walkthrough captured; `v0.1.0` tagged.

---

## 8. GitHub in one page

1. **First commit** is the skeleton; it includes `CODEOWNERS`, `modules.json` and
   CI. Without it, protection cannot require a code owner.
2. **Protect `main`**: one approval, code owner review, `ci / test` and
   `ci / modules`, branch up to date, conversation resolved, no force push, no
   deletion, admins included.
3. **One issue = one module = one branch = one owner = one PR.** Add exactly one
   `module:<id>` label to the issue and the PR.
4. **PR stays under 400 changed lines.** Squash merge. Delete the branch.
5. **Project board:** columns Backlog / Ready / In progress / In review /
   Blocked / Done; fields Seat, Module, Gate, Priority; WIP limit one per person.
6. **CI never executes an ELF** and has no provider key. It runs lint, host tests
   and the module check.
7. **Tags:** `g0-bootstrap`, `fixture-v1`, `audit-v1`, `candidate-v1`, `v0.1.0`.
   Only M1 tags.

Full details and paste-ready configs: [`docs/plan/02-github-workflow.md`](docs/plan/02-github-workflow.md)
and [`docs/plan/04-module-matching.md`](docs/plan/04-module-matching.md).
The one-time setup steps are in
[`docs/plan/05-github-setup-runbook.md`](docs/plan/05-github-setup-runbook.md).

---

## 9. Non-negotiable rules

1. **Never execute the fixture, a candidate, or model-generated code on this
   host.** The guest runner does execution; the host does parsing and rendering.
2. **The contract and corpus are frozen before the AI is called.** The model does
   not write them, and no one edits them to make a plan or patch look better.
3. **The verifier is the only writer of the verdict.** The GUI renders it; the
   AI explains it; neither decides it.
4. **Missing is not passing.** `not_run`, `unverified`, `timed_out` and `skip`
   are never rendered as success.
5. **Source never enters the model prompt.** The analysis and AI modules may read
   the ELF and the contract, never `fixtures/**/build/`.
6. **The provider key stays in one host process.** It never reaches the browser,
   the guest, CI logs, the audit report or the repository.
7. **No weakening a test, oracle, gate or rubric to get green.** Diagnose the
   failure and report it; a change to the criteria needs an ADR and a new gate.
8. **One owner per module.** Do not edit another seat's files; open an issue.
9. **No secrets, client binaries or private logs.** The fixture is public and
   team-built.
10. **Claims are dated and hashed.** A result without a commit, a command and an
    observed output is not evidence.

---

## 10. Glossary

| Term | Meaning |
|---|---|
| MVP2 | This redesigned one-defect, one-route, one-evidence-chain project |
| G0-G4 | The five gates in `docs/plan/00-mvp2-roadmap.md` |
| Contract | The human-reviewed stated criteria (capacity, valid behavior, invalid response, allowed edits) |
| Corpus | The frozen valid/invalid/PoC cases the verifier runs |
| PoC | The 64-byte input that crashes the original |
| `FixPlanV1` | The model's JSON proposal: diagnosis, strategy, edits, coverage, assumptions, uncertainties |
| Audit | The 3-run model evaluation scored against a fixed rubric; G2 |
| `verified_against_stated_criteria` | The only success state; every required check passed on matching hashes |
| Module | A directory with one owner, one interface and one gate; see `modules.json` |
| Guest | The disposable Linux environment that runs the binary; never this host |
| `not_run` | A check that did not execute; not a pass |

---

## 11. What the lead must confirm before G0 closes

- [ ] The five GitHub handles and the M1-M5 mapping in `modules.json`.
- [ ] The gate dates, or the course deadline that replaces them.
- [ ] The fixture: 32-byte buffer, 64-byte PoC, symbols kept (or 64-byte buffer).
- [ ] The repair route: direct binary patch with a trampoline guard (or Route B).
- [ ] The DeepSeek model id and key availability for G2.
- [ ] The repository is the new empty one; the old one is archive.

If any of these changes, update `docs/plan/` and `modules.json` in the same PR;
do not let the documents and the registry drift.

---

## 12. Handing this folder to another person or agent

1. Clone the new repository and open this file.
2. Read the nine documents in section 3, in order.
3. Run `python scripts/check_modules.py --base origin/main` and
   `python -m pytest -q -m "not guest"` to confirm the skeleton is healthy.
4. Pick an issue with one `module:<id>` label from the project board.
5. Create a branch `feat/<module>/<issue>-<slug>`, change only your module, open a
   PR with the same module label.
6. Ask for review from the module owner; M1 merges gate PRs.

If you are an AI agent dropped into this folder, your first response should be a
short summary of the module you own, the artifact you will produce, and the
checks you will run. Do not start by editing shared files.
