# Live AI run interface (G4.1)

- **Status:** draft for implementation, 2026-11-24
- **Owner:** M1 (contract); consumers M2 (gui), M3 (guest, verify), M4 (audit)
- **Related:** ADR 0006, ADR 0005, `docs/interfaces/gui-events-v1.md`, issues #60-#68
- **Not a gate change:** G4 stays signed; the signed replay remains the default and
  the acceptance path. This document only fixes the additive live mode.

## 1. Modes and task fields

```json
{
  "audit_mode": "signed | live",
  "live_guest": true,
  "live_audit": {
    "status": "idle | running | completed | failed",
    "model": "deepseek-v4-pro",
    "started_at": "2026-11-24T02:00:00Z",
    "finished_at": "2026-11-24T02:03:10Z",
    "error": null,
    "runs": [
      {"run_index": 1, "schema_valid": true, "plan_sha256": "…",
       "plan_path": "var/audit/<task>/run-1.json", "usage": {"total_tokens": 24034}}
    ]
  },
  "selected_plan": {
    "source": "signed | live",
    "run_index": 2,
    "path": "var/audit/<task>/selected-plan.json",
    "file_sha256": "…",
    "canonical_sha256": "…"
  }
}
```

- `audit_mode = "signed"` is the current behaviour: `audit` is skipped with
  `satisfied_by_signed_g2` and the repair applies `docs/audit/fix-plan-v1.json`.
- `audit_mode = "live"` requires `live_audit.status = "completed"` and a
  `selected_plan` before the repair can run.
- `live_guest` may be true in either mode (it re-verifies the chosen plan live);
  in live mode it defaults to true.
- The task snapshot never carries a key, a raw provider response or a token.

## 2. API (app/)

All endpoints require the local session; writes require the CSRF header.

### POST /api/tasks/{task_id}/audit/live

Body: `{}` or `{"rerun": true}`.

- Spawns `sys.executable -m pipeline.audit --fixture-dir fixtures/stack-overflow-01
  --runs 3 --raw-dir var/audit/<task>/raw --summary-out var/audit/<task>/summary.json
  --model deepseek-v4-pro` as a child of the API host.
- Injects `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` into **that child's environment
  only** (from `app/assistant_key.py`); the key is never returned, logged or
  persisted.
- 202 `{"status": "running"}`; 409 `audit_no_provider` (no key), `audit_running`,
  `audit_unsupported` (binary not the frozen fixture), `audit_failed` (the child
  failed immediately). A completed audit can be re-run only with `rerun: true`,
  which replaces the previous `live_audit`.
- Timeout 10 minutes; cancellation maps to `live_audit.status = "failed"` with
  `error = "cancelled"`.

### GET /api/tasks/{task_id}/audit

Returns `{"audit_mode", "live_audit"}` (no key, no raw provider response).

### POST /api/tasks/{task_id}/plan

Body: `{"run_index": 2}` or `{"plan_path": "var/audit/<task>/run-2.json"}`.

- Writes `selected_plan`: copies the chosen plan to
  `var/audit/<task>/selected-plan.json` and records `source`, `run_index`, the file
  sha256 and the canonical sha256 (section 6).
- Appends a `user_response` journal record (existing event type) with
  `kind: "plan_selection"` and the same fields, so the console can replay the
  human's choice; the runner reads the task snapshot.
- 409 `plan_unknown` / `plan_not_allowed` (outside the frozen `allowed_edits`) /
  `unsupported_binary_scope`; 422 malformed.
- Does not start the run and does not approve anything.

### Approval binding (POST /api/tasks/{id}/approve)

The body gains optional `expected_plan_sha256`. When `selected_plan` is set, the
API requires it and stores `approval.plan_sha256 = selected_plan.canonical_sha256`.
The runner refuses `live` tasks whose approval lacks that binding
(`plan_not_approved`). The signed mode keeps the existing digest-only approval.

## 3. Runner (scripts/run_task.py)

The runner never reads a provider key and never calls a model.

| Step | signed | live |
|---|---|---|
| audit | `skipped`, `satisfied_by_signed_g2` | `completed` from `live_audit.runs` (exactly 3 rows) and emits `audit_runs`; `failed` with `live_audit_missing` / `live_audit_failed` otherwise |
| decision | `completed` by persisted decision | `completed`; reads `selected_plan` and checks `approval.plan_sha256` (the human's choice is the API's `user_response` with `kind: "plan_selection"`) |
| repair | frozen plan | `selected_plan.path` (inside the repo; `resolve_plan` unchanged) |
| verify | recorded observations | `live_guest`: driver first (section 4), then the verifier with the fresh file |

New reason codes: `live_audit_missing`, `live_audit_failed`, `plan_not_selected`,
`plan_not_approved`, `plan_not_allowed`, `guest_unavailable`, `guest_timeout`,
`guest_observations_invalid`, `observations_candidate_mismatch`.

The terminal rules of ADR 0005 are unchanged: only a run whose required stages
finished ends `completed`; the verdict remains the verifier's.

## 4. Guest driver CLI (guest/, M3)

```text
python guest/live_guest.py \
  --original fixtures/stack-overflow-01/vuln.elf \
  --candidate var/artifacts/<task>/candidate.elf \
  --cases fixtures/stack-overflow-01/cases/cases.json \
  --out-dir var/artifacts/<task>/live-guest \
  [--distro Ubuntu] [--timeout 120] [--keep]
```

Writes:

- `observations-original.json` and `observations-candidate.json` (`ObservationV1`);
- `guest-environment.json`: `{distro, uname, kernel, libc, wsl_version, started_at}`.

Behaviour: fresh `/tmp/binaryrepair-<uuid>/` inside the distro; copy original and
candidate into two fixture dirs with `cases/cases.json`; `chmod +x`; run
`python3 guest/run_cases.py --fixture <dir> --out <obs>` twice; copy the three
files back; clean the guest directory unless `--keep`. The host never executes an
ELF; paths are passed as argv, never through a shell.

Exit codes: `0` ok, `2` bad input (missing file, not ELF64 x86-64, cases
unreadable), `3` guest failure (no `wsl`, distro missing, timeout, copy failure).
WSL2 shares the host network; this is documented in `docs/guest/live-wsl2.md`.

## 5. Audit CLI (pipeline/audit, M4)

```text
python -m pipeline.audit --fixture-dir fixtures/stack-overflow-01 --runs 3 \
  --raw-dir var/audit/<task>/raw --summary-out var/audit/<task>/summary.json \
  --model deepseek-v4-pro
```

`summary.json`:

```json
{"model": "deepseek-v4-pro", "prompt_sha256": "…", "contract_sha256": "…",
 "runs": [{"run_index": 1, "schema_valid": true, "plan_sha256": "…",
           "plan": {…}, "usage": {"total_tokens": 24034}}]}
```

`plan_sha256` remains the response hash (as in G2); the canonical hash below is a
separate value. The raw `run-{i}.json` files stay as evidence. The key comes from
the child environment only.

## 6. Canonical plan hash (M4)

`canonical_plan_hash(plan)` = sha256 of `json.dumps(plan, sort_keys=True,
separators=(",", ":"))` encoded as UTF-8, using the bound plan object exactly as
the audit stored it (identity fields included, as the G2 harness binds them).

Test vector: `docs/audit/fix-plan-v1.json` ->
`6f5f3535f3103acd04665aa4e19a2e8b6075ab7f8bc9657f5f53f01a2693ae1a`.

## 7. Events (gui-events-v1 delta)

- `audit_runs` (existing type) — in live mode `score` is `null` unless a machine
  rubric produced one; `notes` carry the machine checks. Three rows always.
- `user_response` with `kind: "plan_selection"` (existing event type) —
  `{run_index, source, plan_path, file_sha256, canonical_sha256}`; written by the
  API when the human selects, replayable like any GUI record. No new event type is
  introduced, so `app/journal.py` keeps its current vocabulary.
- `verification` kind `guest` — `{status: "passed"|"failed", environment,
  observations_sha256}`.
- `verification` kind `reproduction` (optional) — `{selected_plan_sha256,
  signed_plan_sha256, matched}` when the live plan equals the signed one.
- `error` codes as in section 3; `retry.kind = "manual"` for guest failures.

## 8. Key boundary

The key lives in the API host (`assistant_key.key_path()` or the environment) and is
injected only into the audit child's environment. It is never written to the task
snapshot, the journal, the UI, the guest, a log or the repository; CI has no key.
Missing key => `audit_no_provider` and the UI offers the signed replay.

## 9. Verdict rules (unchanged)

The verifier remains the only writer of the verdict; the six-word vocabulary is
untouched. Live observations must satisfy V0's binding
(`candidate_sha == observations.binary.sha256`) and the frozen corpus/contract.
V4 recognises the declared guard layouts; any other layout yields `unverified`,
never a pass. A live plan outside `allowed_edits` is refused before repair.

## 10. Failure matrix

| Condition | API | Runner | UI |
|---|---|---|---|
| no key | `audit_no_provider` | n/a | badge + replay offer |
| audit running | `audit_running` | n/a | progress stays |
| audit child failed | `live_audit.status = failed` | `live_audit_failed` | stable error code |
| 3 runs not all recorded | — | `live_audit_missing` | no plan cards |
| no plan selected | — | `plan_not_selected` | selection required |
| approval lacks plan hash | — | `plan_not_approved` | re-approve |
| plan outside allowed_edits | `plan_not_allowed` | n/a | refused card |
| no WSL / distro | — | `guest_unavailable` | honest error, no verdict |
| guest timeout | — | `guest_timeout` | honest error |
| observations invalid | — | `guest_observations_invalid` | honest error |
| observation hash mismatch | — | `observations_candidate_mismatch` | honest error |

## 11. Acceptance

- No-key path: the console completes with the signed replay and a truthful badge.
- Fake-child tests cover the API endpoints and the runner stages without a key or
  WSL (CI).
- One real WSL2 run on M3's machine records the frozen fixture + a candidate,
  observations bound to the candidate hash, and a verdict (or an honest
  `unverified`); the commands and hashes go into the G4.1 demo record.
