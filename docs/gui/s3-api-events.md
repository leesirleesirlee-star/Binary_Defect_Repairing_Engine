# S3 API and event-journal console

Status: implemented (S3), 2026-11-20. Interface: `docs/interfaces/gui-events-v1.md`.

## API

`app/api.py` provides session cookie/CSRF, task creation, task snapshot, frozen
contract read/reject, approval binding, start/cancel, SSE replay and the
evidence/export placeholders. `app/journal.py` is the append-only
`var/events/{task_id}.jsonl` validator and tail reader.

## Preview

`POST /api/tasks {"preview":true}` creates a task with `source: synthetic`
events. The UI labels them `合成预览`; every verification check is `not_run`, the
evaluation verdict is `null`, and the terminal run is `failed`. Preview never
produces a success verdict.

## Start

Start requires approval and an `Idempotency-Key`; the API spawns
`scripts/run_task.py` (M1 runner). The runner executes the available analysis
stage and reports not-yet-wired stages as skipped/failed; it never fabricates a
verdict or success. The GUI never imports pipeline modules.

## UI

The generic framework lives in `chat/route-activity.mjs` as two separately
collapsible bordered panels inside the existing route lanes:

- **修复运行监视** (Route A): task discovery, phase, ordered roadmap steps,
  status and artifact links. It is an overview/control surface.
- **事件日志** (Route A, and a Route B placeholder): the chronological SSE
  journal for Route A runs, with event type, seq, step, summary and raw payload.
  The journal envelope has no route field yet, so Route B cannot be attributed;
  it shows an explicit empty state until route attribution is added.

Route A and Route B, the scope area and folded state remain intact; the old
borderless global trace is hidden. No fixture-specific facts, contract criteria,
defect text or input lists are hard-coded; tasks are labelled “修复运行 #N” and
never expose `tsk_...` ids in the UI. The main chat hero has no S2/S3 launch icon.
