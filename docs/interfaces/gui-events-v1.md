# GUI events v1 — browser API and event journal

Status: approved for S3 (M2 console implementation), 2026-11-20.
Owner: M1 contract; consumer: M2 GUI. This document binds the HTTP API and SSE
journal used by `docs/gui/conversation-console-plan.md` §§5.1–5.3.

## 1. Session and CSRF

All write requests require the local session cookie and header `x-csrf-token`.
The token is returned by `GET /api/session`; secrets never reach the browser.

```json
GET /api/session -> 200
{"session": true, "csrf_token": "<csrf>"}
```

Unauthenticated requests return `401` with `{"code":"session_required"}`. A
missing/invalid CSRF token returns `403` with `{"code":"request_forbidden"}`.

## 2. HTTP API

| Method | Path | Request | Success response |
|---|---|---|---|
| GET | `/api/tasks?limit=50` | — | `200 {tasks:[{id,fixture_id,phase,created_at,verdict}]}` |
| POST | `/api/tasks` | multipart `binary` + `defect` + optional `cases`; or JSON `{preview:true, fixture_id}` | `201 {id, phase}` |
| GET | `/api/tasks/{id}` | — | `200 {id, phase, demo, contract{...}, corpus{...}, execution{...}}` |
| GET | `/api/tasks/{id}/contract` | — | `200 {contract, revision, sha256, review_binding_digest}` |
| PUT | `/api/tasks/{id}/contract` | `{expected_revision, contract}` | `200 {revision, sha256, review_binding_digest}`; frozen fixture → `409 frozen_contract` |
| POST | `/api/tasks/{id}/approve` | `{expected_review_binding_digest, reviewer_label}` | `200 {approved, approved_at, binding_digest}`; stale → `409 stale_approval` |
| POST | `/api/tasks/{id}/start` | `{expected_review_binding_digest}`, `Idempotency-Key` | `200 {run_id, phase}`; same key replays; not approved → `409` |
| POST | `/api/tasks/{id}/cancel` | `{run_id}` | `200 {run_id, phase, execution}` |
| GET | `/api/tasks/{id}/events` | SSE | event journal; `Last-Event-ID` replay |
| GET | `/api/tasks/{id}/audit` | — | `AuditReportV1` or `{available:false}` |
| GET | `/api/tasks/{id}/manifest` | — | `EditManifestV1` or `{available:false}` |
| GET | `/api/tasks/{id}/verdict` | — | `VerdictV1` or `{available:false, finalized:false}` |
| GET | `/api/tasks/{id}/artifacts` | — | `{artifacts:[...]}` |
| GET | `/api/artifacts/{artifact_id}` / `/api/artifacts/{artifact_id}/download` | — | metadata / bytes; only owning task |
| GET | `/api/tasks/{id}/export` | — | JSON export bundle |

`verdict.outcome` is exactly the roadmap vocabulary:
`verified_against_stated_criteria`, `rejected`, `unverified`, `unsupported`,
`error`, `not_run`; `null` means not finalized. The GUI never derives it.

## 3. SSE envelope

Every retained journal record has exactly these keys:

```json
{
  "version": 1,
  "type": "run_state",
  "conversation_id": "tsk_...",
  "seq": 7,
  "run_id": "run_...",
  "step_id": "analyze",
  "ts": "2026-11-20T15:00:00Z",
  "source": "runner",
  "payload": {}
}
```

- `seq` is a positive contiguous integer starting at 1. Replay stops at the
  first gap and reports `journal_gap`; it never skips ahead.
- `source` ∈ `runner | verifier | gui | synthetic`.
- SSE `id:` is `seq`; `event:` is the envelope `type`; `data:` is the full envelope.
- Heartbeats are comments (`: heartbeat`) every 15 s and are not journal records.
- `Last-Event-ID` replays records with `seq > id`; absent header replays from 1.
- Queueing, delivery status and replay are presentation semantics: the journal is
  append-only and ordered by `seq`.

## 4. Event payloads

All events carry the envelope above. Unless stated otherwise, data fields are
English ASCII and UI labels are localized by the GUI.

| Type | Payload |
|---|---|
| `user_message` | `{message_id, text, attachment_ids[], delivery}` |
| `message_dispatched` | `{message_id}` |
| `assistant_delta` | `{message_id, append}` |
| `assistant_end` | `{message_id, status}` |
| `thinking` | `{phase: started|finished, duration_ms?, summary_code?}` |
| `tool_call` | `{call_id, tool_code, label_code, input_summary}` |
| `tool_result` | `{call_id, status, duration_ms, output{text,truncated}}` |
| `run_state` | `{job_id?, status, message_id?}` |
| `plan_update` | `{revision, steps:[{step_id,label_code,status}]}`; steps are `collect, freeze, analyze, audit, decision, repair, verify, export` |
| `corpus_update` | `{fixture_id, counts{valid,invalid,poc}, total, cases_sha256}` |
| `awaiting_user` | `{kind: contract_review|audit_decision, request_id, label_code, binding, allowed[]}`; contract binding is `{contract_revision,contract_sha256,corpus_sha256,binary_sha256}`; audit decisions are `proceed|iterate|change_scope` |
| `user_response` | `{kind, request_id, decision, binding?}` |
| `file_change` | `{change_id, stage: proposed|applied, files:[{display_path,added,removed,diff{text,truncated},sha256?}]}` |
| `command` | `{command_id, phase: started|output|finished, label_code, display_cwd, channel?, append?, exit_code?, duration_ms?}` |
| `verification` | `kind: check` → `{level:V0..V4, status:passed|failed|not_run, obligation_id, evidence_ids[], reason_code?}`; `kind: evaluation` → `{evaluation_id, verdict:{outcome, criteria[], coverage, limitations}|null, generated_at}` |
| `audit_runs` | `{report_sha256, runs:[{run_id,schema_valid,score,critical_errors,usable,notes,model,tokens,cost_usd}]}` |
| `error` | `{code, correlation_id, retry{kind}}` |
| `run_end` | `{job_id?, execution, duration_ms, steps_taken, files_changed, ai{calls,tokens,cost_usd}, evaluation_id?}` |

### Required honesty rules

1. `verification.check.status` and `VerdictV1.criteria[].status` use exactly
   `passed / failed / not_run`; `not_run` is rendered verbatim and never converted
   to success.
2. `verification.evaluation.verdict` is `null` until a persisted `VerdictV1`
   exists. The GUI renders `unverified`/`not_run` when it is null.
3. `audit_runs` may contain invalid or missing rows; the GUI displays them as
   persisted, never drops them to make a table look complete.
4. `source: synthetic` events are visibly labelled demo/preview; they cannot
   satisfy acceptance and are never written as real run history.
5. Unknown `reason_code`/`error.code` shows the raw status and an honest
   "unknown reason" label; no inferred cause.

## 5. Journal storage

`var/events/{task_id}.jsonl`, one envelope per line, UTF-8, append-only. The GUI
reads this file and `var/artifacts/` only; it never imports pipeline modules.
`var/tasks/{task_id}.json` stores task metadata and approval binding (no secrets).

A runner (owned by infra, `scripts/run_task.py`) is the only writer of real
journal events. Until it is wired to the pipeline, Start returns an honest
`runner_unavailable` error; S3 preview uses `source: synthetic` only.

## 6. SSE error behavior

- Unknown task → `404`.
- Journal gap or malformed record → emit `event: journal_gap`, then close; never
  silently skip.
- Cancel → runner appends a terminal `run_end`; the GUI closes after it.
- Disconnect does not cancel the run.
