# Binary Defect Repairing Engine (MVP2)

**One defect, one repair route, one evidence chain.**

This repository is a clean redesign of the BinaryRepair project. It repairs one
known stack buffer overflow in a Linux x86-64 ELF without original source, using
an AI-generated repair plan that a human reviews **before** any patch is applied.
A deterministic verifier compares the original and the candidate against a
frozen, human-reviewed contract and regression corpus, and reports
`verified_against_stated_criteria`, `rejected`, `unverified` or `unsupported`.

The model never writes the contract and never decides the verdict. That
separation is the point of the redesign.

> **Status (2026-11-22):** G1 fixture freeze, G2 AI audit and **G3 repair verdict are
> signed** — tags `g0-bootstrap`, `fixture-v1`, `audit-v1`, `candidate-v1`. G4 (the
> end-to-end console demo) is the only gate still open. The verdict is scoped to the
> frozen contract and corpus: **it is not a proof of whole-program correctness or
> security.**
>
> - **G1** — frozen x86-64 fixture, 9-case corpus, contract, original guest
>   observations: [`docs/plan/evidence/G1-RECORD.md`](docs/plan/evidence/G1-RECORD.md).
> - **G2** — three `deepseek-v4-pro` runs on the fixed prompt, rubric scores
>   (M1 99 / M5 100 on the selected plan), decision **`proceed`**:
>   [`docs/plan/evidence/G2-RECORD.md`](docs/plan/evidence/G2-RECORD.md),
>   [`docs/audit/2026-11-21-audit-01.md`](docs/audit/2026-11-21-audit-01.md).
> - **G3** — candidate `c010c006…` produced from the approved plan by the apply CLI;
>   the V0–V5 verifier returned **`verified_against_stated_criteria`** on the guest
>   observations (9/9 cases, canonical verdict hash `51f29be5…`), reproduced
>   independently: [`docs/plan/evidence/G3-RECORD.md`](docs/plan/evidence/G3-RECORD.md),
>   [evidence bundle](docs/plan/evidence/g3/). The guest runtime was a fresh-boot
>   WSL2 VM; strict disposable-guest isolation is recorded as an open limitation.
> - **G4** — the minimal chat-first console (`fb8af46`) and the runner with the G2
>   decision gate and cancellation (`b680a27`) are merged; the end-to-end console
>   demo on the frozen fixture is the remaining gate. The runner needs M3's guest
>   observations and never fabricates a verdict.

## Read first

- [`START-HERE.md`](START-HERE.md) - onboarding for a person or agent opening this folder.
- [`AGENTS.md`](AGENTS.md) - binding rules, safety boundaries, module ownership.
- [`docs/plan/00-mvp2-roadmap.md`](docs/plan/00-mvp2-roadmap.md) - scope and gates.
- [`docs/plan/03-fixture-and-ai-audit-spec.md`](docs/plan/03-fixture-and-ai-audit-spec.md) - fixture, PoC, audit rubric.
- [`docs/gui/conversation-console-plan.md`](docs/gui/conversation-console-plan.md) - the G4 console design (Revision 2.2).
- [`docs/interfaces/gui-events-v1.md`](docs/interfaces/gui-events-v1.md) - runner-to-GUI event contract.
- [`docs/MIGRATION.md`](docs/MIGRATION.md) - what to import from the archive and what not to.

## GUI entry point (fixed URL)

The browser console always opens at **<http://127.0.0.1:8124/welcome>** (archive
at `/ui/`, conversation at `/ui/chat/`). The reference v1.2.2 GUI runs beside it
on <http://127.0.0.1:8125/> and is reachable from the console's「旧版界面」entry
(`/legacy`); the reference GUI links back to the new console.

Double-click `打开GUI.command` (or run `./scripts/open-gui.sh`). The launcher
checks both servers, starts whichever is missing, and opens the fixed URL in the
default browser. Set `BINARYREPAIR_NO_BROWSER=1` to skip opening the page.

## The flow

```text
original ELF + PoC + defect text
        │
        v
[1] contract + corpus (M1/M3, frozen before the AI)          G1 signed
        │
        v
[2] disassembly (M4, deterministic)
        │
        v
[3] AI fix plan (M4, model) ──> [4] human review (G2 hard gate)   G2 signed: proceed
                                      │ approved
                                      v
                          [5] binary patch (M5) ──> candidate ELF   in progress
                                      │
                                      v
                          [6] guest runs original vs candidate (M3)
                                      │
                                      v
                          [7] verdict (M3 verifier) ──> [8] conversation console (M2)
```

Step [8] is a minimal chat-first console: an AI assistant hosts the conversation,
the backend runner walks the roadmap path, and the right-side panels show the
live run monitor and event journal.

## Repository layout

```text
app/                  FastAPI + the conversation console (api.py, journal.py, static/ui/)
fixtures/             one 32-byte stack-overflow sample, PoC, corpus
guest/                isolated runner; the only place a binary executes
pipeline/analyze/     ELF facts and disassembly view
pipeline/ai/          provider transport and prompt builder
pipeline/audit/       three-run audit harness and report
pipeline/repair/      cave finder, patch writer, edit manifest
pipeline/verify/      deterministic checks and verdict writer
prompts/              versioned prompt templates (no source material)
schemas/              ContractV1, FixPlanV1, ObservationV1, VerdictV1, CandidateV1, ...
scripts/              repository checks and the task runner (run_task.py)
docs/plan/            the current plan, ownership and GitHub rules
docs/adr/             architecture decision records (0001-0004)
docs/interfaces/      frozen handoff contracts between seats
docs/archive/         curated v1.2.2 documents, read-only reference
var/                  runtime artifacts (gitignored; never committed)
```

Every path belongs to exactly one module in [`modules.json`](modules.json). A PR
must carry exactly one `module:<id>` label and must not change files outside that
module.

## Checks

```bash
python -m pip install -r requirements.txt
ruff check .
python -m pytest -q -m "not guest"
python scripts/check_modules.py --base origin/main
```

`guest` tests are excluded here. They run only in the disposable guest with the
frozen fixture; CI never executes an ELF.

## What this project does not claim

- Not general exploitability, not "the program is secure".
- Not whole-program correctness or a formal proof.
- Not coverage of stripped, real-world or client binaries.
- Not a production product.

The full limitations live in [`docs/plan/00-mvp2-roadmap.md`](docs/plan/00-mvp2-roadmap.md)
and will be repeated next to every verdict.

## Archive

The accepted v1.2.2 project is kept at
<https://github.com/leesirleesirlee-star/Binary_Repair>. It is read-only
reference: its evidence, tags and verdicts do not apply to this repository.

## License

MIT. See [`LICENSE`](LICENSE).
