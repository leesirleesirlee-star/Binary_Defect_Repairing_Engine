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

> **Status (2026-11-21):** G1 fixture freeze and G2 AI audit are signed — tags
> `g0-bootstrap`, `fixture-v1`, `audit-v1`. G3 (patch + verify) and G4
> (conversation console) are in progress. **No verified repair exists yet; this
> is not a working product.**
>
> - **G1** — frozen x86-64 fixture, 9-case corpus, contract, original guest
>   observations: [`docs/plan/evidence/G1-RECORD.md`](docs/plan/evidence/G1-RECORD.md).
> - **G2** — three `deepseek-v4-pro` runs on the fixed prompt, rubric scores
>   (M1 99 / M5 100 on the selected plan), decision **`proceed`**:
>   [`docs/plan/evidence/G2-RECORD.md`](docs/plan/evidence/G2-RECORD.md),
>   [`docs/audit/2026-11-21-audit-01.md`](docs/audit/2026-11-21-audit-01.md).
> - **G3** — repair CLI merged; `CandidateV1` published (ADR 0004). The V0-V4
>   verifier ([#11](https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine/issues/11))
>   and the applied candidate are still open.
> - **G4** — the minimal chat-first conversation console (plan Revision 2.2,
>   live run panels) is implemented on branch `gui/complete-mvp2-2026-11-21`;
>   the task runner is on `main`. The console itself is not merged yet.

## Read first

- [`START-HERE.md`](START-HERE.md) - onboarding for a person or agent opening this folder.
- [`AGENTS.md`](AGENTS.md) - binding rules, safety boundaries, module ownership.
- [`docs/plan/00-mvp2-roadmap.md`](docs/plan/00-mvp2-roadmap.md) - scope and gates.
- [`docs/plan/03-fixture-and-ai-audit-spec.md`](docs/plan/03-fixture-and-ai-audit-spec.md) - fixture, PoC, audit rubric.
- [`docs/gui/conversation-console-plan.md`](docs/gui/conversation-console-plan.md) - the G4 console design (Revision 2.2).
- [`docs/interfaces/gui-events-v1.md`](docs/interfaces/gui-events-v1.md) - runner-to-GUI event contract.
- [`docs/MIGRATION.md`](docs/MIGRATION.md) - what to import from the archive and what not to.

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
