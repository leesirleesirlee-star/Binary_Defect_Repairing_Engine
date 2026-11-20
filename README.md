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

> **Status:** G0, repository bootstrap. The GitHub repository is empty and this
> tree is the local skeleton. No fixture, no AI call, no patch and no verdict
> exist yet. Do not describe this as a working repair tool.

## Read first

- [`START-HERE.md`](START-HERE.md) - onboarding for a person or agent opening this folder.
- [`AGENTS.md`](AGENTS.md) - binding rules, safety boundaries, module ownership.
- [`docs/plan/00-mvp2-roadmap.md`](docs/plan/00-mvp2-roadmap.md) - scope and gates.
- [`docs/plan/03-fixture-and-ai-audit-spec.md`](docs/plan/03-fixture-and-ai-audit-spec.md) - fixture, PoC, audit rubric.
- [`docs/MIGRATION.md`](docs/MIGRATION.md) - what to import from the archive and what not to.
- [`docs/plan/04-module-matching.md`](docs/plan/04-module-matching.md) - module registry and CI scope check.

## The flow

```text
original ELF + PoC + defect text
        │
        v
[1] contract + corpus (M1/M3, frozen before the AI)
        │
        v
[2] disassembly (M4, deterministic)
        │
        v
[3] AI fix plan (M4, model) ──> [4] human review (G2 hard gate)
                                      │ approved
                                      v
                          [5] binary patch (M5) ──> candidate ELF
                                      │
                                      v
                          [6] guest runs original vs candidate (M3)
                                      │
                                      v
                          [7] verdict (M3 verifier) ──> [8] GUI / evidence (M2)
```

## Repository layout

```text
app/                  FastAPI + Jinja GUI (thin server; renders only)
fixtures/             one 32-byte stack-overflow sample, PoC, corpus
guest/                isolated runner; the only place a binary executes
pipeline/analyze/     ELF facts and disassembly view
pipeline/ai/          provider transport and prompt builder
pipeline/audit/       three-run audit harness and report
pipeline/repair/      cave finder, patch writer, edit manifest
pipeline/verify/      deterministic checks and verdict writer
prompts/              versioned prompt templates (no source material)
schemas/              ContractV1, FixPlanV1, ObservationV1, VerdictV1
scripts/              repository checks, including the module scope check
docs/plan/            the current plan, ownership and GitHub rules
docs/archive/         curated v1.2.2 documents, read-only reference
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
