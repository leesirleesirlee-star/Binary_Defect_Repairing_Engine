# MVP2 planning package

**Status:** proposal for team review, 2026-11-20. Nothing here is approved yet.
**Target repository:** <https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine> (empty, default branch `main`).
**Reference repository:** <https://github.com/leesirleesirlee-star/Binary_Repair> (v1.2.2, kept as the accepted archive).
**Reference report:** `f1780f3c300e4d75adcdefbfc5fd1dec.pdf` (19 November 2026), "AI-Assisted Binary Vulnerability Repair: Project Workflow and Technical Assessment".

## What this package decides

1. **What the new MVP is.** One simple stack overflow, one proof-of-concept input, one AI repair plan reviewed by humans, one binary repair route, one deterministic evidence chain.
2. **Where every file lives.** A small repository tree with one owner per module.
3. **Who owns what.** Five seats, one owner per module, no shared edit surfaces.
4. **How GitHub is run.** Branch protection, PR size and review rules, issue and project conventions, CI that never executes a binary.

## Documents

| File | Purpose |
|---|---|
| [`00-mvp2-roadmap.md`](00-mvp2-roadmap.md) | Why the reset, scope, phases, gates, target tree, risks |
| [`01-team-ownership.md`](01-team-ownership.md) | Five-seat division, file ownership matrix, interface handoffs, conflict rules |
| [`02-github-workflow.md`](02-github-workflow.md) | Repository setup, branch/PR/issue/project/CI/release rules, paste-ready configs |
| [`03-fixture-and-ai-audit-spec.md`](03-fixture-and-ai-audit-spec.md) | Fixture, PoC, corpus, disassembly view, AI audit protocol and rubric |
| [`04-module-matching.md`](04-module-matching.md) | Module registry, `CODEOWNERS`, CI scope check, project labels and the exact module matching rules |
| [`05-github-setup-runbook.md`](05-github-setup-runbook.md) | The one-time GitHub setup: push, labels, ruleset, project, first issues, negative test of the module check |

## The one-paragraph version

The previous project proved that the team can build a large, honest acceptance
machine, but it also showed the real bottleneck: when the AI writes the contract,
the repair and the evaluation, agreement between candidates is not independent
evidence. The new MVP therefore keeps the **evidence discipline**, drops the
scope to **one 32-byte stack overflow**, and puts a **human-reviewed contract and
regression corpus** between the AI and the verdict. The first gate is not a
patch: it is an **audit of whether the model can produce a usable repair plan
from disassembly alone** under fixed criteria. If the plans are usable but
correctness cannot be established, the project invests in verification, not in a
bigger model. That is exactly the decision rule in the reference report.

## Approval needed before any implementation

- [ ] Repository choice: use the empty `Binary_Defect_Repairing_Engine`, not the archived `Binary_Repair`.
- [ ] Five-seat mapping (who is M1-M5) and GitHub handles.
- [ ] One repair route for MVP2: direct binary patch (trampoline guard).
- [ ] Fixture size (32-byte buffer) and contract wording.
- [ ] Provider and key availability for the AI audit.
- [ ] Dates for the five gates in `00-mvp2-roadmap.md`.

After approval, the first implementation PR is **M1's repository skeleton only**;
feature directories start as separate PRs so no two people edit the same files.
