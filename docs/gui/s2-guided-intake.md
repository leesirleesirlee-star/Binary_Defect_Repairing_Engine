# S2 guided intake — frozen G1 fixture

Status: implemented on `m2/gui-console-s1` (S1+S2), 2026-11-20.

## Surface

The chat page now uses the generic Route A run monitor (`chat/route-activity.mjs`).
No sample-specific contract, fixture facts, defect text, input lists or hashes are
rendered in the execution pane. The S2 guided-intake module remains in the tree for
the task-bound approval API, but it is not loaded by the chat page and does not
appear below Route A/B.

## API slice

- `GET /api/fixture` — read-only fixture display
- `POST /api/tasks` — create the bound task
- `POST /api/tasks/{id}/approve` — bind the review digest; stale digest → 409
- `PUT /api/tasks/{id}/contract` — always 409 `frozen_contract`
- `POST /api/tasks/{id}/start` — starts the real runner after approval

## Tests

`tests/app/test_fixture_snapshot.py` checks 9 cases, persisted hashes, schema
validity, deterministic binding, approval, stale rejection and the non-success
initial state. `tests/app/test_api.py` covers the task-bound approval and real
runner start. `tests/app/test_ui_preview_assets.py` covers the new assets.
