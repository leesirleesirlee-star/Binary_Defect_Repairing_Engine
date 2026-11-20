# Five-seat ownership: one owner per layer, no shared edit surfaces

**Status:** proposal, 2026-11-20
**Basis:** the reference report's separation of expectations, repair and
verification; the v1.2.2 team roles; the MVP2 scope in `00-mvp2-roadmap.md`.

## 1. Principles

1. **One owner per path.** A directory or file has exactly one person allowed to
   change it. Everyone else opens an issue or comments on a PR.
2. **Expectations before repair.** The contract and the regression corpus are
   written and frozen by people who do not write the repair.
3. **Verification is independent of repair.** The person who applies the patch
   never signs the verdict.
4. **Interfaces are files, not chat.** A handoff is a JSON artifact with a schema
   and a hash, committed or attached to the PR.
5. **Small PRs, short branches.** Target under 400 changed lines per PR; no
   branch lives longer than five working days.
6. **Five seats, five owners.** The previous Lead + M1-M5 split is collapsed into
   five. M1 carries the lead/integration duty; there is no separate VMer seat.

## 2. The five seats

The GitHub handles below were confirmed by the team on 2026-11-20. The seat
definitions, not the names, are the proposal; a future swap changes the names
here, in `modules.json` and in `CODEOWNERS`, and nothing else.

| Seat | Provisional GitHub | One-line mission |
|---|---|---|
| **M1** | `@leesirleesirlee-star` | Lead / contracts and integration: repo, CI, schemas, merge, release, gate sign-off |
| **M2** | `@huajinyao` | GUI and thin API: four screens, evidence rendering, screenshots |
| **M3** | `@chenfanaichifan` | Fixture and verification: C sample, PoC, corpus, guest runner, deterministic verdict |
| **M4** | `@hxw64` | Analysis and AI audit: disassembly, prompt, provider, rubric, audit report |
| **M5** | `@lyz200807` | Repair implementation: ELF editing, guard stub, candidate, edit manifest |

If the team prefers to keep the historical M-numbers, keep the **path ownership**
and swap only the names. Do not split a path between two people.

### M1 - Lead / contracts and integration

**Mission.** Keep the evidence chain honest and the repository moving. M1 is the
only person who can change the contract, the schemas, the CI, the branch
protection and the release tags.

**Owns**

```text
.github/**            CODEOWNERS, PR/issue templates, CI
README.md             status, scope, limitations
AGENTS.md             binding rules for coding agents
CONTRIBUTING.md       branch/PR/review rules
SECURITY.md           secret and client-data rules
pyproject.toml        dependencies, ruff, pytest config
schemas/**            JSON Schemas + examples
docs/plan/**          this package
docs/adr/**           architecture decisions
docs/interfaces/**    frozen handoff artifacts
scripts/**            repo-wide bootstrap/check scripts only
docs/README.md        documentation map
```

**Delivers.** Protected `main`; green CI; frozen `ContractV1`, `FixPlanV1`,
`ObservationV1`, `VerdictV1`; merged PRs with owner approval; dated gate records;
release tags; final limitations statement.

**Does not own.** Fixture C code, analysis code, repair code, GUI templates,
verifier implementation. M1 reviews them but does not edit them.

**First three tasks.** (1) Create the repository skeleton and protection.
(2) Write the contract and schemas v0. (3) Set up the project board and the
weekly gate review.

### M2 - GUI and thin API

**Mission.** Make the evidence chain visible without ever deciding it. The GUI
renders persisted JSON; it does not compute a verdict, a pass rate or a success
label.

**Owns**

```text
app/**                FastAPI app, routes, templates, static assets
tests/app/**          render, API and honesty tests
docs/gui/**           flow, screenshots, copy deck
```

**Delivers.** Four screens: task, analysis, verification, evidence. Upload or
fixture selection, disassembly view, AI plan card with assumptions and
uncertainty, plan approval control, candidate-vs-original results table, verdict
banner from `verdict.json`, downloads. Chinese UI labels, English data fields.
`not_run` rendered verbatim. Honesty tests: no success without a verdict, no
synthetic percentage, missing artifact shown as missing.

**Does not own.** Contract wording, analysis prompts, repair logic, verdict
logic, schema changes.

**First three tasks.** (1) Reuse the v1.2.2 visual shell and build a static
four-screen prototype against example JSON. (2) Agree the screen data contract
with M1. (3) Write render tests with `not_run` and missing-data cases.

### M3 - Fixture and verification

**Mission.** Own the ground truth that the AI and the repair are measured
against: one simple vulnerable program, one PoC, one frozen corpus, one runner,
one deterministic verifier.

**Owns**

```text
fixtures/**           C source (build-only), binary, manifest, cases
guest/**              runner, isolation notes, observation capture
pipeline/verify/**    deterministic checks and verdict computation
tests/fixture/**      build, corpus, runner and verifier tests
docs/fixture/**       provenance, build recipe, corpus rationale
```

**Delivers.** `vuln.elf` with pinned build flags and hash; `poc.bin`; valid and
invalid corpora; `observations-original.json` (PoC crashes, valid cases pass);
`observations-candidate.json`; `verdict.json` in the fixed vocabulary. M3 signs
the fixture freeze with M1 and independently re-runs M5's candidate.

**Does not own.** The contract text (M1 owns it, M3 reviews), the AI prompt, the
repair, the GUI. M3 must not edit the contract to make a candidate pass.

**First three tasks.** (1) Write and build the 32-byte fixture; record flags and
hashes. (2) Author the PoC and the corpus. (3) Build the case runner and capture
the original observations.

### M4 - Analysis and AI audit

**Mission.** Turn an ELF into a faithful disassembly view, ask the model for a
repair plan under the frozen contract, and score the plans honestly. This seat
also owns the first gate: is the model's plan good enough to implement?

**Owns**

```text
pipeline/analyze/**   ELF facts, function slice, disassembly view, FindingV1
pipeline/ai/**        provider client, prompt builder, output schema validation
pipeline/audit/**     run harness, rubric, report generator
prompts/**            versioned prompt templates (no source material)
tests/analysis/**     disassembly, prompt separation, schema tests
docs/analysis/**      design notes
docs/audit/**         audit reports and raw outputs
```

**Delivers.** `disassembly.json`; `FindingV1`; `FixPlanV1` for 3 runs; prompt and
response hashes; token usage; rubric table; dated audit report with a
`proceed`/`iterate`/`change_scope` recommendation. The prompt contains no source
path, no source text and no reference fix; a test enforces that.

**Does not own.** The contract, the corpus, the repair, the verdict. M4 never
grades its own prompt against a criterion it wrote; M1 and M5 review the rubric
before the runs.

**First three tasks.** (1) Build the disassembly view and prove it contains no
source. (2) Draft the prompt and `FixPlanV1`; review with M1/M5. (3) Run 3 audits
on the frozen fixture and write the report.

### M5 - Repair implementation

**Mission.** Convert the approved plan into the smallest possible byte-level
change, record every edit, and hand a candidate to M3 for verification. M5 does
not sign the verdict.

**Owns**

```text
pipeline/repair/**    cave finder, stub assembler, patch writer, edit manifest
tests/repair/**       patch, manifest, boundary and idempotency tests
docs/repair/**        design notes, rejected alternatives
```

**Delivers.** `candidate.elf`; `edit-manifest.json` (offset, vaddr, original
bytes, new bytes, reason); a reproducible patch script; a candidate that differs
from the original only in the manifest. The stub checks length, tail-calls
`strcpy` on the valid path, writes the exact error line and exits 1 on the
invalid path.

**Does not own.** The plan (M4 proposes, M1/M3/M5 approve), the contract, the
verdict, the GUI. M5 may build generic ELF editing primitives before G2 but must
not apply a repair to the fixture before the audit gate.

**First three tasks.** (1) Build the cave finder and read-only ELF inspector.
(2) Write the patch writer with a dry-run manifest. (3) Prepare the guard-stub
assembler and its boundary tests, without touching the fixture.

## 3. File ownership matrix

`CODEOWNERS` is the enforcement. This table is the human-readable version.

| Path | Owner | May review | May not edit |
|---|---|---|---|
| `.github/**`, `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml` | M1 | all | all |
| `schemas/**`, `docs/interfaces/**`, `docs/adr/**`, `docs/plan/**`, `scripts/**` | M1 | all | all |
| `app/**`, `tests/app/**`, `docs/gui/**` | M2 | M1 | M3, M4, M5 |
| `fixtures/**`, `guest/**`, `pipeline/verify/**`, `tests/fixture/**`, `docs/fixture/**` | M3 | M1, M5 | M2, M4 |
| `pipeline/analyze/**`, `pipeline/ai/**`, `pipeline/audit/**`, `prompts/**`, `tests/analysis/**`, `docs/analysis/**`, `docs/audit/**` | M4 | M1, M5 | M2, M3 |
| `pipeline/repair/**`, `tests/repair/**`, `docs/repair/**` | M5 | M1, M3 | M2, M4 |
| `docs/archive/**` | M1 | all | all (read-only) |
| `var/**` | nobody | - | committed by nobody; gitignored |

**Shared file rule.** There is no shared edit surface. If two seats need a change
in `schemas/` or `docs/interfaces/`, M1 opens one PR and the consumers adapt in a
follow-up. Do not send two PRs against the same schema file.

## 4. Interface handoffs

Every handoff is a JSON file with a schema, a producer and a consumer. A chat
message is only a notification; the artifact is the handoff.

| ID | Artifact | Producer | Consumer | Schema | Frozen at |
|---|---|---|---|---|---|
| H1 | `contract.json` | M1 (review M3) | M2, M3, M4, M5 | `ContractV1` | G1 |
| H2 | `fixture-manifest.json` | M3 | M4, M5 | `FixtureManifestV1` | G1 |
| H3 | `cases/{valid,invalid,poc}.json` | M3 | M4 (PoC only), M5 (no), verifier | `CaseSetV1` | G1 |
| H4 | `disassembly.json` + `FindingV1` | M4 | M1, M5, M2 | `DisassemblyViewV1` | G2 |
| H5 | `fix-plan.json` (3 runs) | M4 | M1, M3, M5 | `FixPlanV1` | G2 |
| H6 | `audit-report.md` + raw responses | M4 | all | report template | G2 |
| H7 | `candidate.elf` + `edit-manifest.json` | M5 | M3, M2 | `EditManifestV1` | G3 |
| H8 | `observations-*.json` | M3 | M2, M1 | `ObservationV1` | G3 |
| H9 | `verdict.json` | M3 (deterministic verifier) | M2, M1 | `VerdictV1` | G3 |
| H10 | `evidence-bundle.json` | M1 assembles | M2, report | `EvidenceBundleV1` | G4 |

Rules:

- A consumer may not start its step until the producer's artifact is committed
  with a SHA-256.
- A producer may not change a frozen artifact without a new version and an ADR.
- The verifier consumes H7 and H8, not a chat description of the patch.

## 5. RACI per gate

R = responsible, A = accountable, C = consulted, I = informed.

| Gate | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|
| G0 plan / repo | **A/R** | C | C | C | C |
| G1 fixture freeze | **A** | I | **R** | C | C |
| G2 AI audit | **A** | I | C | **R** | C |
| G3 candidate verified | **A** | I | **R** | C | **R** |
| G4 GUI / delivery | **A** | **R** | C | C | C |

No gate is signed by the person who produced the thing being gated:

- G2 is signed by M1 after M4's report; M5 reviews implementability; M3 confirms
  the contract and corpus did not change.
- G3 is signed by M1 after M3's verdict; M5 does not sign.
- G4 is signed by M1 after M2's demo; M2 does not sign the honesty review alone.

## 6. Parallel start plan

So nobody waits for the first PR to land:

| Seat | Can start on day 1 | Depends on |
|---|---|---|
| M1 | Repo skeleton, protection, schemas, ADR template, CI | nothing |
| M2 | Static four-screen prototype on example JSON; reuse v1.2.2 CSS | M1's screen data contract (draft is enough) |
| M3 | C fixture, PoC, corpus, guest runner | contract draft from M1 |
| M4 | ELF facts + disassembly view on the v1.2.2 fixture; prompt draft | M3's fixture manifest (can use an older ELF meanwhile) |
| M5 | ELF cave finder and patch writer dry-run | M3's fixture (read-only) |

The first integration point is G1, not a big-bang merge. Until G1, each seat
works in its own directory on its own branch.

## 7. Conflict rules

1. **Never edit a file you do not own.** Open an issue with the `area:` label.
2. **One issue, one branch, one owner.** Do not share a branch.
3. **Branch from `main` every morning.** Rebase before opening a PR. Never merge
   `main` into a feature branch with unrelated changes.
4. **Keep PRs under 400 changed lines** (excluding generated fixture bytes and
   docs). Split by layer, not by file count.
5. **No repo-wide formatting.** Run `ruff format` only on the files you changed.
6. **Do not move or rename another seat's files.** Directory moves need an ADR
   and M1's PR.
7. **Freeze means freeze.** After G1, the contract, corpus and fixture hash are
   immutable for MVP2; a change is a new version and a new gate.
8. **Do not "fix" a failing check by relaxing it.** Diagnose, report the failing
   case, and fix the cause; if the check is wrong, change it in an ADR with M1.
9. **No secrets, client binaries or private logs.** The guest never receives the
   provider key; the browser never receives it either.
10. **If two tasks need the same file, sequence them.** M1 schedules the order;
    the later owner rebases after the first PR merges.

## 8. Rework and escalation

- A failed PR returns to its owner, not to a new person.
- A blocked seat reports the blocking artifact and the exact missing input; the
  weekly review reassigns only after the blocker is recorded.
- A disagreement about scope or evidence goes to M1; if it changes the contract
  or the verdict vocabulary, it becomes an ADR, not a chat decision.
- The team records the same-person limitation honestly: five students, no
  external auditor. The mitigation is role separation plus re-runs, not a claim
  of independent review.

## 9. Workload estimate

Part-time, including review time:

| Seat | P0 | P1 | P2 | P3 | P4 | Total |
|---|---|---|---|---|---|---|
| M1 | 4d | 2d | 2d | 2d | 2d | ~12d |
| M2 | 3d | 1d | 1d | 3d | 5d | ~13d |
| M3 | 1d | 6d | 1d | 5d | 1d | ~14d |
| M4 | 1d | 2d | 6d | 2d | 1d | ~12d |
| M5 | 1d | 2d | 3d | 6d | 1d | ~13d |

The numbers are planning aids, not commitments. If one seat is overloaded, move
a self-contained sub-task to an idle seat only with M1's recorded reassignment;
do not silently edit another owner's directory.
