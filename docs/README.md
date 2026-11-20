# Documentation map

## Current authority

| Document | Purpose |
|---|---|
| [`../START-HERE.md`](../START-HERE.md) | onboarding for a person or agent opening this folder |
| [`../AGENTS.md`](../AGENTS.md) | binding rules for coding agents |
| [`plan/00-mvp2-roadmap.md`](plan/00-mvp2-roadmap.md) | scope, phases, gates, target tree |
| [`plan/01-team-ownership.md`](plan/01-team-ownership.md) | five seats, interfaces, conflict rules |
| [`plan/02-github-workflow.md`](plan/02-github-workflow.md) | branch/PR/issue/project/CI/release |
| [`plan/03-fixture-and-ai-audit-spec.md`](plan/03-fixture-and-ai-audit-spec.md) | fixture, PoC, audit protocol, G2 |
| [`plan/04-module-matching.md`](plan/04-module-matching.md) | module registry and CI scope check |
| [`MIGRATION.md`](MIGRATION.md) | what to import from the v1.2.2 archive and what not |
| [`interfaces/README.md`](interfaces/README.md) | frozen handoff artifacts H1-H10 |
| [`adr/0000-template.md`](adr/0000-template.md) | decision record template |

If a current document conflicts with the archive, the current document wins.

## Per-module documentation

| Folder | Owner | Contents |
|---|---|---|
| `fixture/` | M3 | build recipe, provenance, corpus rationale |
| `analysis/` | M4 | disassembly design and source-separation notes |
| `audit/` | M4 | audit reports, raw responses, rubric decisions |
| `repair/` | M5 | patch design, rejected alternatives, edit manifests |
| `gui/` | M2 | flow, copy deck, screenshots, reference assets |

## Archive

`docs/archive/` holds curated v1.2.2 documents. They explain the previous,
larger project and are read-only reference. They are not current evidence and
their verdicts do not apply here. See [`archive/README.md`](archive/README.md).

## Gate records

Gate records live in `docs/plan/records/` (created at G0) and follow the template
in `plan/02-github-workflow.md` section 12. A gate record without a commit, a
command and an observed output is not a record.
