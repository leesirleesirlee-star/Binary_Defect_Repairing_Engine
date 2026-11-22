# GUI events v1 — journal, SSE and runner contract

- **Version:** 1 (frozen for G2–G4)
- **Producer:** the runner (`scripts/run_task.py`, `infra`) for run events; the GUI for conversation events; the verifier only for `verification` events it owns
- **Consumer:** `app/journal.py` (validation and tail), `app/api.py` (SSE replay)
- **Decision:** ADR 0003

The GUI reads `var/events/{task_id}.jsonl` and `var/artifacts/` and never imports
a `pipeline/*` module. This document is the only contract between the two sides.
Where the plan (`docs/gui/conversation-console-plan.md` §5) and this document
differ, this document wins for v1 and the change needs an ADR.

## 1. Journal file

- Path: `var/events/{task_id}.jsonl`, one JSON object per line, UTF-8, append-only.
- `task_id` matches `^[A-Za-z0-9._-]{1,128}$`.
- A record is at most 1,000,000 bytes; a larger record is a hard error.
- `seq` starts at 1 and is contiguous with no gaps. A gap fails the read closed
  (`JournalGap`); the reader never skips ahead.
- Readers tolerate a partially written final line only by ignoring it until it is
  complete; writers append one line per event and `fsync`.

## 2. Envelope

Every record has exactly these envelope fields plus `payload`:

| Field | Type | Rule |
|---|---|---|
| `version` | integer | `1` |
| `type` | string | one of §3 |
| `conversation_id` | string | the task id for run events |
| `seq` | integer | `>= 1`, contiguous per file |
| `run_id` | string or null | present for run events, stable for the whole run |
| `step_id` | string or null | one of §4 |
| `ts` | string | RFC 3339 UTC, e.g. `2026-11-20T15:12:03.123Z` |
| `source` | string | `runner`, `verifier`, `gui` or `synthetic` |
| `payload` | object | per §3; never a string, never an array |

Example:

```json
{"version":1,"type":"plan_update","conversation_id":"tsk_ab12cd34ef56ab78cd90ef12","seq":7,"run_id":"run_7f3a","step_id":"analyze","ts":"2026-11-20T15:12:03.123Z","source":"runner","payload":{"revision":1,"steps":[]}}
```

## 3. Event types

The GUI keeps the sixteen v1.2.2 types and adds two for MVP2
(`corpus_update`, `audit_runs`). The runner emits only the ones marked R; the GUI
emits the conversation ones; `verification` is owned by the verifier when it
lands.

| Type | Who | Payload |
|---|---|---|
| `user_message` | GUI | GUI-internal |
| `message_dispatched` | GUI | GUI-internal |
| `assistant_delta` | GUI | GUI-internal |
| `assistant_end` | GUI | GUI-internal |
| `thinking` | GUI | GUI-internal |
| `tool_call` | GUI | GUI-internal |
| `tool_result` | GUI | GUI-internal |
| `run_state` | R | `{status: "running"\|"cancelled"\|"failed"\|"completed", message_id: string\|null}` |
| `plan_update` | R | `{revision: int, steps: [{step_id, label_code, status}]}`, status \in `pending / in_progress / completed / failed / skipped` |
| `corpus_update` | R | `{fixture_id, counts: {valid, invalid, poc}, total, cases_sha256}` |
| `awaiting_user` | R | `{request_id, kind: "audit_decision", allowed: ["proceed","iterate","change_scope"], binding: {contract_revision, contract_sha256, corpus_sha256, binary_sha256}}` |
| `user_response` | GUI | GUI-internal |
| `file_change` | R | `{change_id, stage: "proposed"\|"applied", files: [{display_path, added, removed, diff: {text, truncated}}]}`; display paths only, never absolute host paths |
| `command` | R | `{command_id, phase: "started"\|"output"\|"finished", label_code, display_cwd, exit_code: int\|null}`; `output` adds `text, truncated` |
| `verification` | R/V | `kind: "check"`: `{level: "V0".."V4", status: "passed"\|"failed"\|"not_run", obligation_id, evidence_ids: [], reason_code: string\|null}`; `kind: "evaluation"`: `{evaluation_id, verdict: null\|six-word, generated_at}` |
| `audit_runs` | R | `{report_sha256: hex64\|null, runs: [{run_index, schema_valid, score: int\|null, critical_errors: [], usable, notes}]}`; always three rows once emitted, invalid JSON included |
| `error` | R | `{code, correlation_id, retry: {kind: "manual"\|"none"}}`; `code` is a stable string, no stack traces |
| `run_end` | R | `{execution: "completed"\|"failed"\|"cancelled", duration_ms, steps_taken, files_changed, ai: {calls: int\|null, tokens: int\|null, cost_usd: number\|null}, evaluation_id: string\|null}` |

Rules that are honesty-critical:

1. `verification.evaluation.verdict` is `null` until the verifier finalizes; the
   GUI renders only the persisted `VerdictV1.verdict` and never infers it.
2. `run_end.ai` values are `null` when the provider did not report them; the GUI
   shows "not provided", never a guess.
3. A run that did not reach a verdict ends with `execution: "failed"` and, before
   that, an `error` with a stable `code`. Success is never synthesized.
4. Synthetic preview events use `source: "synthetic"` and can never satisfy
   acceptance.

## 4. Step ids

```text
collect -> freeze -> analyze -> audit -> decision -> repair -> verify -> export
```

`plan_update` carries the whole checklist every time (revision increments). A
stage that has not started is `pending`; a stage that cannot run in the current
gate is `skipped` with a following `error`/`not_run` record, never `completed`.

## 5. Runner CLI contract

```bash
python -m scripts.run_task --task <task_id> --var-root var
```

- Reads `var/tasks/{task_id}.json` (the GUI-written task snapshot).
- Refuses to run unless `approval.approved` is true and
  `approval.binding_digest == review_binding_digest`; otherwise exit code `3`
  and no journal events.
- **G2 hard stop at the last execution point:** `repair` and `verify` run only when
  a persisted `proceed` decision exists — the task snapshot `decision` field
  (preferred), else the latest journal `user_response` with
  `payload.kind == "audit_decision"`. Without a persisted decision those stages are
  `skipped` with code `decision_missing`; a persisted `iterate` / `change_scope`
  refuses them with `decision_not_proceed`. The runner never invents a decision and
  never reports success in those cases.
- **Cancellation reaches the process:** the GUI records `execution.status =
  "cancelled"` (or `execution.cancel_requested = true`) in the task snapshot; the
  runner polls it, terminates the running child (SIGTERM, then kill), appends
  exactly one terminal `run_end` with `execution: "cancelled"` and exits with code
  `5`. A cancelled run is never reported as still running or as success.
- Appends `source: "runner"` events for one `run_id`; exactly one terminal
  `run_end` per run.
- Writes artifacts under `var/artifacts/{task_id}/` and events that point at them
  by `display_path` only.
- Exit codes: `0` journal written and terminated (even when stages are `not_run`),
  `2` invalid task or journal, `3` not approved / stale binding, `4` internal error
  after a terminal `run_end` was written, `5` cancelled after a terminal `run_end`
  with `execution: "cancelled"` was written.
- Prints one JSON summary to stdout: `{task_id, run_id, execution, reason_code, events}`.
- Never reads a provider key; the audit stage's own CLI owns that, and the runner
  records only the provider id/usage the audit reports.

## 6. What this contract does not cover

- SSE transport details (heartbeat, `Last-Event-ID` reconnect) — GUI-owned.
- Artifact registry and download endpoints — later S-stage; the runner only writes
  files under `var/artifacts/{task_id}/` and names them in `file_change`.
- Provider prompts and responses — `pipeline/ai` and the audit report own those.
