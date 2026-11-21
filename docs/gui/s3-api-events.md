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

The generic framework lives in `chat/route-activity.mjs` as a nested, collapsible
panel inside the existing Route A lane. Route A and Route B, the scope area and
the trace area remain intact. The panel reads `/api/tasks` and each task's SSE
journal; it renders plan steps in roadmap order, every event with sequence and raw
payload, analysis/artifacts, and live updates for up to twelve real (non-preview)
tasks. No fixture-specific facts, contract criteria, defect text or input lists
are hard-coded in the framework; each task is identified by its task id and phase.
The main chat hero has no S2/S3 launch icon.
