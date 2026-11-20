# ADR 0003: the conversation console replaces the four-screen GUI, and the runner is infra-owned

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** M1 (lead); M2, M3, M4, M5 informed
- **Supersedes:** the four-screen scope of issue #12

## Context

The GUI plan (`docs/gui/conversation-console-plan.md`, merged in #33) replaces the
four-screen G4 scope with the conversation console reused from v1.2.2. Two open
decisions block the mainline:

1. the GUI change needs a written decision so `docs/plan/00-mvp2-roadmap.md`,
   `START-HERE.md` and issue #12 can be rewritten;
2. the event-journal seam needs an owner: the GUI may read `var/events/**` and
   `var/artifacts/**` but must never import `pipeline/{analyze,ai,audit,repair,verify}`,
   so somebody has to execute the pipeline and append events.

## Decision

1. **G4 scope.** The conversation console is the GUI. `/welcome`, `/ui/chat/` and
   the read-only `/ui/` evidence archive stay separate surfaces. The four-screen
   scope in #12 is superseded.
2. **Runner ownership.** A single runner at `scripts/run_task.py` under the
   `infra` module (M1) executes the pipeline **as subprocess CLIs** and appends
   journal events. It does not import GUI code; it does not import pipeline code
   either — subprocess keeps the module dependency graph acyclic.
3. **Event interface.** `docs/interfaces/gui-events-v1.md` is the binding contract
   between runner and GUI (envelope, event types, payloads, runner CLI). Both
   sides code against it; the GUI validates on read, the runner validates before
   append.
4. **Honesty.** Until a stage's CLI is merged and wired, the runner emits
   `not_run`/`failed` with a reason code and never a fabricated success, score or
   verdict. The terminal `run_end` is `failed` while any stage is unwired.

## Consequences

- M1 maintains `scripts/run_task.py`; GUI Start asks the runner for a run id and
  tails the journal.
- M2's S3 acceptance (`?preview=1`) is unaffected; real Start flips from
  `503 runner_unavailable` to a real run only when the runner is present.
- Issues #7/#8/#9/#11 gain the "emits events per `gui-events-v1`" criterion.

## Alternatives rejected

- **A new `runner` module:** more registry churn for one script; `infra` already
  owns `scripts/`.
- **GUI spawns pipeline CLIs directly:** violates the GUI's forbidden-import and
  honesty boundary (the GUI would parse pipeline output and could infer success).
- **Runner imports pipeline modules:** acyclic module graph is worth more than
  avoiding subprocess overhead for a local MVP.
