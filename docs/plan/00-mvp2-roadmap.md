# MVP2 roadmap: one defect, one route, one evidence chain

**Status:** proposal, 2026-11-20
**Target:** `leesirleesirlee-star/Binary_Defect_Repairing_Engine` (empty repository)
**Reference:** `leesirleesirlee-star/Binary_Repair` v1.2.2 (accepted archive, do not modify)
**Inputs reviewed:** the 2026-11-19 technical assessment report; the v1.2.2 codebase and docs; the current team assignment records.

## 1. Why reset

The v1.2.2 project is a complete course deliverable: two repair routes, a V0-V5
acceptance ladder, 827 passing tests, a large workbench UI, connector and plugin
inventories, nine UI languages, and a long evidence history. It over-serves the
MVP and makes one question hard to answer:

> If the AI drafts the verification contract, proposes the repair, and its
> candidates are then compared against that contract, what exactly is being
> verified?

The 2026-11-19 report names this the **test oracle problem**. The intended
behavior of a compiled binary is underdetermined by the binary, one failing
input, and a short defect description. Removing the observed failure does not
show that normal functionality survived. The report's recommendations are:

1. establish expected behavior independently of the repair proposal;
2. test candidates against independent reference behavior and regression tests;
3. report evidence-backed states, not adjectives: **verified against stated
   criteria**, **unverified**, **unsupported**;
4. separate model quality from contract quality, and keep the criteria constant
   when comparing them.

MVP2 takes those four points as its architecture.

## 2. Research question and claim

**Question.** How can AI-assisted binary repair establish reliable evidence of
correctness when the original program's intended behavior is incompletely
specified?

**What MVP2 will demonstrate.** For one simple stack overflow, with a
human-reviewed contract and regression corpus fixed before the model is called:
the team can (a) obtain a usable repair plan from disassembly alone, (b)
implement that plan as a byte-level patch, and (c) report
`verified_against_stated_criteria`, `rejected`, `unverified` or `unsupported`
with the exact evidence and unresolved uncertainty.

**What MVP2 will not claim.**

- Not general exploitability or "the program is secure".
- Not whole-program correctness or a formal proof.
- Not that the model's explanation is evidence.
- Not coverage of stripped, real-world or client binaries.

## 3. Product flow

```text
original ELF ──┐
PoC + output ──┼─> [1] independent contract ──> [2] disassembly ──> [3] AI fix plan
defect text  ──┘        (human reviewed)             (deterministic)      (model)
                                                                              │
                                    [4] human plan review <─────────────────┘
                                                │ approved
                                                v
                              [5] binary patch ──> candidate ELF
                                                │
                              [6] guest runs original vs candidate on the frozen corpus
                                                │
                              [7] deterministic verdict: verified / rejected / unverified / unsupported
                                                │
                              [8] minimal chat-first conversation console: evidence and export
```

The order matters. The contract and corpus are frozen **before** the AI audit.
The model sees the disassembly, the defect description, the contract criteria and
the allowed edit scope, but not the source, the hidden corpus, or the reference
fix. The model never writes the contract and never produces the verdict.

## 4. Scope

### In scope

| Area | MVP2 content |
|---|---|
| Fixture | One CWE-121-style stack buffer overflow: `char buf[32]`, unbounded `strcpy`, Linux x86-64, non-PIE, no stack protector, symbols kept |
| PoC | One 64-byte input (`A` x 64) that crashes the original with SIGSEGV |
| Corpus | Valid: 0, 1, 5, 31 bytes; invalid: 32, 33, 64, 128 bytes; boundary at 31/32 |
| Contract | Human-written and frozen: capacity 32 including NUL, max valid 31, invalid input prints the exact error line to fd 2 and exits 1, no stdout, no write past `buf[31]` |
| Analysis | ELF facts, function slice for `handle`, capstone disassembly, the `call strcpy@plt` site, stack frame size |
| AI audit | DeepSeek, disassembly-only prompt, `FixPlanV1` JSON, 3 independent runs, fixed rubric, human review |
| Repair | One route: 5-byte `call` redirect to a guard stub in an executable cave; stub checks length, tail-calls `strcpy`, otherwise `write(2)` + `exit_group(1)` |
| Verification | V0 identity, V1 structure, V2 valid behavior, V3 invalid/PoC behavior, V4 boundary, optional V5 re-apply reproducibility |
| GUI | Minimal chat-first conversation console (reuse of the v1.2.2 chat UI): one AI-hosted chat thread collects binary + normal/crash inputs, freezes the contract, narrates the three-run audit, asks for the decision and ends with the download; corpus/contract/event/score details stay hidden and live only in the evidence entry and the download bundle. `app/loader.py` + `app/render.py` stay the honesty core; verdict and `not_run` render verbatim; no `pipeline.*` import |
| Delivery | README, demo script, evidence bundle, report section with limitations |

### Out of scope for MVP2

Route B decompile/recompile, symbolic execution, formal V5 replay, multiple
fixtures, stripped binaries, arbitrary uploads, LLM chat assistant, connectors,
plugins, nine-language UI, server-side history, LAN sharing, real client data.

These are not deleted from the record; they stay in the archived v1.2.2 repository
and can return after the MVP2 evidence chain is accepted.

## 5. Result vocabulary

Use exactly these words in code, GUI and report. Do not invent a second success
label.

| State | Meaning |
|---|---|
| `verified_against_stated_criteria` | Every required criterion passed on matching original/candidate hashes. Scope is the written contract, nothing more. |
| `rejected` | At least one required criterion failed on the final candidate. |
| `unverified` | A required check did not run, was inconclusive, timed out, or the evidence does not bind to the final bytes. |
| `unsupported` | The request is outside the declared scope (wrong arch, wrong defect class, missing contract). |
| `error` | A tool or provider failed before a verdict could be computed. |
| `not_run` | One individual check did not execute. Never rendered as a pass. |

`verified_against_stated_criteria` is the only success state, and it is produced
by the deterministic verifier, never by the GUI, the model, or a route handler.

## 6. Target repository tree

The repository starts empty. Import only what MVP2 needs; do not copy the whole
v1.2.2 tree.

```text
.
├─ README.md                  # what this is, status, limitations, quick start
├─ AGENTS.md                  # binding rules for coding agents (safety + ownership)
├─ CONTRIBUTING.md            # branch/PR rules, checks, review expectations
├─ SECURITY.md                # reporting, secret rules, no client data
├─ LICENSE                    # MIT
├─ pyproject.toml             # dependencies, ruff, pytest config
├─ .github/                   # CODEOWNERS, PR/issue templates, CI
├─ docs/
│  ├─ README.md               # map; current docs vs archive
│  ├─ plan/                   # this package
│  ├─ adr/                    # architecture decision records (one file per decision)
│  ├─ interfaces/             # frozen handoff artifacts between seats
│  ├─ fixture/                # M3 design notes and provenance
│  ├─ analysis/               # M4 design notes
│  ├─ audit/                  # M4 AI audit reports (the gate)
│  ├─ repair/                 # M5 design notes and edit manifests
│  ├─ gui/                    # M2 design notes, screenshots
│  └─ archive/                # curated v1.2.2 docs kept read-only
├─ fixtures/
│  └─ stack-overflow-01/
│     ├─ build/               # C source + build script (BUILD-ONLY, never read by analysis)
│     ├─ vuln.elf             # compiled original, committed
│     ├─ manifest.json        # hashes, flags, symbols, segment facts
│     ├─ contract.json        # frozen contract (owned by M1, reviewed by M3)
│     └─ cases/               # valid.json, invalid.json, poc.json
├─ guest/
│  ├─ run_cases.py            # runs one ELF against the corpus, writes observations
│  └─ README.md               # isolation, snapshot, timeout, capture rules
├─ pipeline/
│  ├─ analyze/                # ELF parsing + disassembly view + FindingV1
│  ├─ ai/                     # provider client, prompt builder, FixPlanV1 schema
│  ├─ audit/                  # audit runner + rubric + report generator
│  ├─ repair/                 # cave finder, patch writer, edit manifest
│  └─ verify/                 # deterministic V0-V4 checks + verdict writer
├─ app/                       # minimal chat-first console: FastAPI API + AI-hosted chat UI (read-only data, no verdict logic)
│  ├─ main.py                 # surfaces: /welcome, /ui/chat/, read-only /ui/
│  ├─ api.py                  # session/CSRF, tasks, approve/start/cancel, SSE replay
│  ├─ journal.py              # append-only event-journal reader/validator
│  ├─ loader.py, render.py    # honesty core: persisted JSON in, six-word verdict out
│  └─ static/ui/              # chat, welcome, workbench (v1.2.2 reuse, adapted)
├─ schemas/                   # JSON Schemas + examples (owned by M1)
├─ tests/
│  ├─ contract/               # schema and result-state tests (M1)
│  ├─ fixture/                # fixture + corpus + runner tests (M3)
│  ├─ analysis/               # disassembly/prompt/schema tests (M4)
│  ├─ repair/                 # patch/manifest tests (M5)
│  └─ app/                    # render/API/honesty tests (M2)
├─ scripts/                   # repo-wide bootstrap/check scripts only (M1)
└─ var/                       # gitignored runtime logs, jobs, observations
```

### What is imported from v1.2.2

| Import | Destination | Owner | Rule |
|---|---|---|---|
| `app/templates/` + `app/static/` visual assets | `app/` | M2 | Keep the look; rewrite routes and data contracts |
| `binaryrepair_ai/` transport (client, errors, settings) | `pipeline/ai/` | M4 | Adapt the import surface; do not copy the old candidate schema |
| Selected contract/verification docs | `docs/archive/` | M1 | Read-only reference, not current authority |
| `fixtures/public/CWE121...` | not imported | - | Stays in the archive; MVP2 uses a new, simpler fixture |
| `artifacts/`, `routea/`, `routeb/`, `workers/`, `tools/`, `plugins/`, `knowledge/`, `data/` | not imported | - | Available in the archived repository |

### Why this tree

- Every directory has one owner, so no two people edit the same file.
- The analysis code physically cannot read `fixtures/**/build/`: it receives an
  ELF path and a contract object, never a source path.
- The GUI has no acceptance code; it renders `verdict.json`.
- `schemas/` is the only cross-seat edit surface and is owned by M1.

## 7. Phases and gates

Dates assume part-time work by five students. Shift them only with a recorded
decision; do not silently re-baseline a gate.

| Phase | Calendar | Goal | Owner (R) | Gate |
|---|---|---|---|---|
| **P0 Bootstrap** | Nov 20-24 | empty repo becomes a governed skeleton | M1 | **G0**: plan approved; `main` protected; CI green; schemas v0; five seats accepted |
| **P1 Fixture + PoC** | Nov 25-Dec 1 | one overflow, one PoC, frozen corpus | M3 | **G1**: fixture tagged `fixture-v1`; original crashes on PoC; valid cases pass; contract frozen |
| **P2 AI audit** | Dec 2-Dec 8 | disassembly -> 3 AI plans -> human review | M4 | **G2**: audit report signed; one plan approved; decision `proceed` / `iterate` / `change_scope` |
| **P3 Repair + verify** | Dec 9-Dec 17 | approved plan -> candidate -> evidence | M5 / M3 | **G3**: candidate passes V0-V4; verifier returns `verified_against_stated_criteria`; independent re-run |
| **P4 GUI + delivery** | Dec 18-Dec 24 | minimal chat-first console flow (AI-hosted chat), demo, report | M2 | **G4**: end-to-end demo through the console on the real fixture; honesty tests; headless walkthrough; `v0.1.0` |
| Buffer | Dec 25-31 | fixes, report, presentation | M1 | final submission |

### Gate G2 is a hard stop

No repair implementation PR is merged before G2. M5 may build ELF editing
primitives and tests during P1/P2, but must not apply a fix to the fixture until
the audit report approves a plan. This is the user's requirement: confirm the
repair plan first, then proceed.

### Gate decision rule (from the report)

After the audit, the team records one of:

- **`proceed`** - at least one plan is usable and implementable; move to P3.
- **`iterate`** - plans are close but fail a specific rubric item; revise the
  prompt/context and rerun, up to 3 rounds, with the same contract and corpus.
- **`change_scope`** - no usable plan after 3 rounds. Then the product becomes
  "AI-assisted analysis + human-authored patch", and the report says so.

Do not weaken the contract, the corpus or the rubric to turn `iterate` into
`proceed`.

## 8. Risks and mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| AI writes the contract | Circular evidence, the report's central warning | Contract is authored by M1, reviewed by M3, frozen before the AI call; the prompt receives it read-only |
| AI plan is plausible but unimplementable | Wasted P3, false confidence | Rubric item "implementable within allowed edits"; M5 reviews every plan before G2 |
| Model produces no usable plan | Project scope is wrong | G2 decision rule `change_scope`; report the failure honestly |
| PoC crash is environment-specific | Evidence does not reproduce | Pinned build flags, hashes, guest snapshot, recorded kernel/toolchain; PoC re-run twice |
| Valid behavior under-specified | "No crash" is mistaken for correct | Independent valid corpus fixed before repair; boundary cases; stdout/exit-code comparison |
| GUI becomes the verdict | Honesty defect | Verdict module is the only writer; GUI renders `verdict.json`; honesty tests |
| Host executes the binary | Safety violation | All execution in the guest runner; CI never executes an ELF; host tests use fake observations |
| Five people collide | Merge conflicts, lost work | One owner per path; CODEOWNERS; small PRs; file ownership matrix |

## 9. Open decisions

1. **Repo:** confirm `Binary_Defect_Repairing_Engine` is the only active repo and
   `Binary_Repair` becomes read-only archive.
2. **Seats:** confirm the five GitHub handles and the M1-M5 mapping in
   `01-team-ownership.md`.
3. **Fixture:** confirm 32-byte buffer and the exact stderr line. A 64-byte buffer
   with a 128-byte PoC is the alternative if 32 feels too small.
4. **Provider:** DeepSeek key availability and the exact model id. If no key, G2
   is `unverified`, not faked.
5. **Dates:** confirm the P0-P4 calendar or replace it with the course deadline.
6. **Report format:** whether the final deliverable must include the research
   question and the negative results, not only the demo.

## 10. Definition of done for MVP2

- The original ELF crashes on the PoC and passes the valid corpus; both are
  recorded with hashes and raw outputs.
- The contract and corpus were frozen before the AI audit; the freeze is a dated
  record.
- The AI audit report contains 3 raw plans, a rubric table, a human decision and
  the model/prompt hashes.
- The candidate ELF differs from the original only in the recorded edit manifest;
  all required checks pass on matching hashes.
- The verdict is `verified_against_stated_criteria`, with scope and limitations
  written next to it.
- The GUI is the conversation console; it never computes a verdict and only the runner executes the pipeline.
- `main` is green, protected, and every merged PR has an owner approval.
