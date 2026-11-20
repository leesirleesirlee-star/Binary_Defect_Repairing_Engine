# M2 GUI plan — conversation repair console (maximum reuse of the v1.2.2 chat UI)

- **Status:** Draft for M2, 2026-11-20 (Asia/Shanghai). Decision recorded here pending the mainline
  decision record (ADR 0002 or G4 milestone note, see §10).
- **Module:** `gui` (M2). Paths: `app/`, `tests/app/`, `docs/gui/`. Gate: G4, delivered in stages
  aligned with the G1–G3 mainline (§7).
- **Supersedes:** the four-screen scope of issue #12 and `docs/gui/schema-review.md`
  (kept as a historical record).
- **Reuse source:** archived `Binary_Repair` v1.2.2 (`b885d21`), conversation UI under
  `app/static/ui/`; design authority:
  `docs/handoff/2026-11-17-conversation-ui-design.md` (information architecture + SSE event
  contract), `docs/handoff/2026-11-17-conversation-ui-wireframes.md`,
  `docs/interfaces/frontend-backend-contract-v1.md`, `docs/architecture/agent-console.md`.

## 1. Decision: do not redesign the UI, change functionality and interfaces only

The v1.2.2 third-generation conversation UI (welcome → `/ui/chat/` → `/ui/` archive) becomes the
MVP2 GUI. The user flows into a chat where the agent guides intake (binary + normal inputs + crash
input), the backend walks the roadmap path (analyze → 3-run audit → G2 decision → patch → verify),
and the chat ends with downloads (repaired ELF + accompanying files). The chat remains usable like
a normal AI assistant between and around the gated actions.

Two kinds of change, nothing else:

1. **Functionality:** intake questions, card contents, labels, verdict vocabulary, and the mapping
   of run activity to the MVP2 pipeline steps.
2. **Interfaces:** the browser API and SSE payloads are rewritten against the MVP2 schemas; a local
   event-journal seam replaces the legacy controller/worker backend.

Stays byte-identical in behavior: component tree, layout, CSS (`chat.css` / `glass.css` /
`steps.css`), welcome and archive surfaces, composer mechanics (Enter/Shift+Enter/IME composition,
queue-while-running, Stop), streaming text, replay via `Last-Event-ID`, sidebar/settings,
keyboard focus, reduced-motion behavior, and the EN/zh-CN locale switcher.

## 2. Copy list from the archived repo

| Source (archived `Binary_Repair` v1.2.2) | Destination (this repo) | Notes |
|---|---|---|
| `app/static/ui/chat/` (all `.mjs`, `index.html`, 3 CSS) | `app/static/ui/chat/` | as-is; payload rendering adapted in §3 |
| `app/static/ui/workbench/` (all files) | `app/static/ui/workbench/` | archive surface: task list + evidence view |
| `app/static/ui/welcome/` (all files) | `app/static/ui/welcome/` | entry surface |
| `app/static/ui/shared/`, `app/static/ui/assets/`, `app/static/ui/index.html`, `app/static/ui/workbench.html`, `app/static/ui/README.md` | same paths | shared DOM/icon/theme helpers |
| `tests/test_ui_preview_assets.py` (pattern) | `tests/app/test_ui_preview_assets.py` | asset/module resolution tests |
| `app/api_v1.py` (pattern only) | `app/api.py` (rewritten) | session/CSRF/version-header pattern; no legacy routes |

Do **not** copy: `app/backend.py`, `app/controller_api.py`, `app/domain/**`, `app/db/**`,
`app/services/**` (forbidden by `docs/MIGRATION.md`), the Jinja app (`templates/`, `static/js/`),
connector/plugin pages, `routea/`, `routeb/`, `workers/`.

## 3. Functional changes: the guided flow rewritten to the MVP2 path

The chat walks the roadmap path; each step renders as an activity row in the transcript:

| # | Step | Card / activity (data source) |
|---|---|---|
| 0 | intake | attach binary (client-side SHA-256, ELF-magic warning that does not block), defect description (ASCII), normal inputs (valid samples), crash input (PoC). For the frozen MVP2 fixture these render read-only from `fixtures/stack-overflow-01/cases.json`; arbitrary uploads that require capturing original behavior are L1 (`docs/plan/06-agent-roadmap.md` §5), out of MVP2 scope. |
| 1 | corpus + contract | `CaseSetV1` summary (case counts, `cases_sha256`) and the `ContractV1` card: `stated_criteria`, `allowed_edits`, `diagnostic_hypothesis` flagged as a hypothesis (not a criterion), `binary_sha256`, `criteria_source: human_frozen`. MVP2 freezes both **before** the AI call (G1): the frozen fixture card is read-only; a changed contract is a new freeze (new task). |
| 2 | review / approve | approval card binds `{revision, contract_sha256, corpus_sha256, binary_sha256}` (the v1.2.2 `review_binding_digest` pattern). Deny is a local decision. Start stays blocked until approved. |
| 3 | run | explicit Start with an `Idempotency-Key`; Stop requests cancellation. `plan_update` checklist: collect → freeze → analyze → audit ×3 → decision → repair → verify → export. |
| 4 | analyze (#7) | `DisassemblyViewV1` activity: ELF facts, function slice, `call strcpy@plt` site; `FindingV1` card with `status: hypothesis / confirmed_by_analysis / refuted`. |
| 5 | audit (#8/#9) | three `FixPlanV1` run cards: per-run `schema_valid`, `score`, `critical_errors`, `usable`, `notes`; rubric table (§6.5 of the audit spec); per-run AI usage (model, tokens, cost). The **G2 decision card** offers `proceed` / `iterate` / `change_scope` and stays in the transcript. Invalid-JSON runs stay visible. Raw responses (key removed, hashed) live under Evidence. |
| 6 | repair (#28) | `EditManifestV1` diff card: `patch_site`, `cave`, `trampoline` blob, `edits[]` with original/patch bytes. Dry-run stage shows `candidate_written: false`; after `proceed`, the applied stage shows the `file_change` with the candidate hash. **G2 hard stop:** no repair activity renders before the decision card is approved. |
| 7 | verify (#11) | guest observation rows per case (original vs candidate: exit, signal, stdout, stderr) and the `VerdictV1` card: verdict in the six-word vocabulary, per-criterion `pass / fail / not_run`, coverage, limitations. `not_run` renders verbatim, never as a pass. |
| 8 | summary + download | download links: **repaired ELF**, `EditManifestV1`, `VerdictV1`, `AuditReportV1`, raw responses, export bundle. The legacy manual-deliverable upload is removed. |

Free chat: user messages that are not intake answers are answered like a normal assistant; they
never enter `FixPlanV1`, the audit report or the verdict. The three audit runs are produced only by
the fixed prompt, so chat cannot coach a run (§3 of `docs/plan/03-fixture-and-ai-audit-spec.md`).

## 4. Label and vocabulary changes

- `workbench/labels.mjs`: verdict six words (`verified_against_stated_criteria`, `rejected`,
  `unverified`, `unsupported`, `error`, `not_run`); criterion status `pass / fail / not_run`;
  decision `proceed / iterate / change_scope`; mode badge `deterministic / llm` (plus the honest
  `llm (not wired)` state); fallback banner shows a localized `fallback_code`, never raw provider
  text; missing metrics show "not provided", never invented zeros.
- Remove the `route_a / route_b` axis everywhere; the single route is the trampoline guard. The
  archive cards drop the route column.
- Chinese labels, English data (roadmap §4): the shell's EN/zh-CN switcher is kept.

## 5. Interface changes

### 5.1 Browser API (rewrite of the v1 contract; fresh repo, no dual-wire legacy)

| Method | Path | Request → success response |
|---|---|---|
| GET | `/api/session` | `200 {session: true, csrf_token}` |
| GET | `/api/tasks?limit=50` | `200 {tasks: [{id, fixture_id, phase, created_at, verdict}]}` |
| POST | `/api/tasks` | multipart: `binary` + `defect` + optional `cases` (normal/crash inputs as text or JSON) → `201 {id, phase}`; 20 MiB file / 16 KiB text limits, 413/422 as in the v1 contract |
| GET | `/api/tasks/{id}` | task snapshot: `id`, `phase`, `demo`, `contract` (ContractV1 + revision/approved/sha256), `corpus` (CaseSetV1 summary), `execution {run_id, status, terminal, reason_code}` |
| GET/PUT | `/api/tasks/{id}/contract` | read / update with `expected_revision` (frozen fixture: update rejected `409`); `200 {revision, sha256, review_binding_digest}` |
| POST | `/api/tasks/{id}/approve` | `{expected_review_binding_digest, reviewer_label}` → `200 {approved, approved_at}`; content-hash-only approval is rejected `409 stale_approval` |
| POST | `/api/tasks/{id}/start` | `{expected_review_binding_digest}` + `Idempotency-Key` → `200 {run_id, phase}`; same key replays the same acknowledgement |
| POST | `/api/tasks/{id}/cancel` | `{run_id}` → `200 {run_id, phase, execution}` |
| GET | `/api/tasks/{id}/events` | SSE event journal for the task; `Last-Event-ID` replay from zero or the last contiguous sequence (§5.3) |
| GET | `/api/tasks/{id}/audit` | `200` AuditReportV1 (or `available: false` while unfinalized) |
| GET | `/api/tasks/{id}/manifest` | `200` EditManifestV1 (dry-run) |
| GET | `/api/tasks/{id}/verdict` | `200` VerdictV1 (finalized) or `{available: false, finalized: false}` — pending is never success |
| GET | `/api/tasks/{id}/artifacts`, `/api/artifacts/{id}`, `/api/artifacts/{id}/download` | artifact metadata / download; only the owning task; `409 artifact_unavailable` on integrity failure |
| GET | `/api/tasks/{id}/export` | JSON export bundle (verdict + manifest + audit + artifact list) |

Every JSON/multipart write requires the session cookie and `x-csrf-token`. Provider secrets never
reach the browser: a provider-status endpoint returns only `{configured, provider_id}`.

### 5.2 SSE event contract (delta against the v1.2.2 design doc)

Keep the 16 event types, the envelope (`version/conversation_id/seq/run_id/step_id/ts/source`),
queueing, delivery status, replay and heartbeat semantics. Payload changes:

| Event | Change |
|---|---|
| `verification.check` | `level` ∈ V0–V4 (V5 optional); `status` ∈ `passed / failed / not_run` (VerdictV1 vocabulary); `obligation_id` = `VerdictV1.criteria[].id`; drop the route field |
| `verification.evaluation` | `verdict.outcome` ∈ the six-word set; `null` until the verifier finalizes |
| `awaiting_user` | `contract_review` binding becomes `{contract_revision, contract_sha256, corpus_sha256, binary_sha256}`; new request kind `audit_decision` with allowed decisions `proceed / iterate / change_scope` |
| `run_end` | `ai.{calls, tokens, cost_usd}` comes from the audit harness (`AuditReportV1.model` + per-run usage) |
| `plan_update` | step checklist = collect → freeze → analyze → audit ×3 → decision → repair → verify → export |
| `file_change` | `proposed` = EditManifestV1 edits; `applied` = candidate bytes with its hash |
| `command` | guest rows for `run_cases.py` invocations (started/output/finished, exit code); display paths only |
| new `corpus_update` | CaseSetV1 summary after intake: case counts, `cases_sha256` |
| new `audit_runs` | the three-run table from AuditReportV1: per-run `schema_valid / score / critical_errors / usable` |

### 5.3 Event-journal seam (new mainline item)

The GUI app reads `var/events/{task_id}.jsonl` and `var/artifacts/` only, and never imports
`pipeline/{analyze,ai,audit,repair,verify}` (`modules.json` forbidden paths). A **runner** executes
the pipeline CLIs in roadmap order and appends events to the journal; the SSE endpoint tails the
journal and serves replay. The runner is not M2 work — see §7. Until the runner exists, M2 develops
against `?preview=1` synthetic events, exactly as the v1.2.2 shell did.

## 6. Honesty rules (test-locked, mapped from `agent-console.md` §三)

1. Verdict renders only from the persisted `VerdictV1.verdict`; the GUI never infers or aggregates.
   `app/loader.py` + `app/render.py` stay as the tested honesty core.
2. `not_run`, `missing`, `timed_out` render verbatim; they are never success.
3. The mode badge tells the truth (`deterministic / llm / llm (not wired)`); a fallback always shows
   the banner with its localized code.
4. Missing `model`/`tokens` show "not provided", never invented numbers.
5. Unknown `reason_code` shows "unknown reason + report the status file", never a guess.
6. Creation and Start are user-initiated only; the assistant never starts a run or writes a verdict.
7. Model text is data: escaped, quoted, never executed; prompt-injection text in raw responses is
   displayed as data.
8. Demo/synthetic events are visibly labelled and can never satisfy acceptance.

## 7. Mainline merge (this plan replaces the four screens in the mainline)

| Mainline object | Action | Owner |
|---|---|---|
| issue #12 | rewrite scope to this plan (proposed body in Appendix A) | Lead / M1 |
| `docs/plan/00-mvp2-roadmap.md` §3 (flow diagram), §4 (GUI row), §7 (G4 criteria) | replace four-screen wording with the conversation console; needs the decision record | M1 |
| `START-HERE.md` §7 G4 checklist | rewrite to the console checklist | M1 |
| `docs/interfaces/gui-events-v1.md` | new contract doc: §5.1 + §5.2 as the binding interface | M1 (M2 proposes) |
| issues #7, #8, #9, #11 | add acceptance criterion: "emits events per `docs/interfaces/gui-events-v1.md`" | M4 / M3 |
| `modules.json` + `CODEOWNERS` | decide runner ownership: minimal path is `scripts/run_task.py` under `infra` (M1); a new `runner` module is the alternative | M1 |
| `docs/gui/README.md`, `schema-review.md` banner | mark the four-screen notes superseded | M2 (first PR) |

M2 stage plan with mainline dependencies:

| Stage | M2 work | Mainline dependency | Gate |
|---|---|---|---|
| S1 shell | copy static tree, asset tests, welcome/chat/archive open | none (PR #30 merged first for schemas) | G2 pre |
| S2 intake + contract | wizard questions, corpus card, ContractV1 card, approval card | none — renders the frozen fixture | G2 pre |
| S3 API + events | `app/api.py`, SSE journal reader, §5.2 rendering | `docs/interfaces/gui-events-v1.md` approved | G2 |
| S4 audit UI | three-run cards, rubric, decision card, raw responses | #9 merged (and #7 for analyze rows) | G2 |
| S5 repair + verify UI | manifest diff card, observation rows, verdict card, downloads | #28 + #11 merged | G3 |
| S6 evidence + honesty | archive wiring, honesty tests, headless walkthrough, demo fixtures, screenshots | S5 | G4 |

## 8. M2 task breakdown (PR-sized, ≤400 changed lines, one `module:gui` label each)

| Task | Content | Blocks on |
|---|---|---|
| T-GUI-1 | static UI copy + `test_ui_preview_assets` port + supersede banners | none |
| T-GUI-2 | intake wizard: binary attach, defect, normal-inputs list, crash-input card | none |
| T-GUI-3 | corpus card + ContractV1 card + approve/deny card with binding digest | none |
| T-GUI-4 | `app/api.py` (session/CSRF/tasks/contract/approve/start/cancel) | §5.1 approved |
| T-GUI-5 | SSE reader + event rendering for analyze/audit/repair/verify + labels | §5.2 approved |
| T-GUI-6 | verdict card, evidence surface, artifact download, export | #11 merged |
| T-GUI-7 | demo fixtures, headless Edge walkthrough, screenshots, G4 evidence | S6 |

Each PR ships with `tests/app/*` additions; no PR imports `pipeline.verify/repair/ai` or touches
another module's paths.

## 9. Acceptance criteria

- S1: `/welcome`, `/ui/chat/`, `/ui/` open from the repo root; all asset tests pass; no Jinja legacy.
- S2: attach the frozen fixture → corpus card shows 9 cases → contract card shows the frozen
  ContractV1 → approve binds the three digests; editing a frozen contract is rejected.
- S3: `?preview=1` replays a synthetic journal covering all §3 steps with correct rendering.
- S4: three audit runs render with scores/critical errors; decision card restricts the next step;
  `iterate` re-runs are visible; invalid JSON stays in the table.
- S5: manifest diff card shows dry-run `candidate_written: false`; verdict card shows the six-word
  verdict; `not_run` verbatim; downloads resolve to the registered artifacts.
- S6 (G4): end-to-end demo on the frozen fixture: attach → approve → three-run audit → proceed →
  candidate → verdict → download bundle; headless Edge walkthrough captured; honesty tests green;
  `v0.1.0` tagged.

## 10. Open decisions for the Lead

1. Record the decision replacing the four-screen G4 with the conversation console (ADR 0002 or a G4
   milestone note), so M1 can edit the roadmap docs.
2. Runner ownership: `scripts/run_task.py` under `infra` (M1, recommended) vs a new `runner` module
   in `modules.json` + `CODEOWNERS`.
3. Keep `/ui/` archive and `/welcome` as separate surfaces (recommended: yes — maximum reuse and a
   read-only evidence library).
4. Transport: SSE with a 2 s polling fallback, as the v1.2.2 baseline did.

## Appendix A — proposed replacement body for issue #12

> **Title:** Conversation repair console (reuse the v1.2.2 chat UI)
>
> Replace the four-screen scope with the conversation console in
> [`docs/gui/conversation-console-plan.md`](conversation-console-plan.md): copy the archived
> `app/static/ui/` tree unchanged, rewrite functionality and interfaces to the MVP2 path
> (binary + normal/crash inputs → contract freeze → three-run audit → decision → patch → verify →
> download repaired ELF + accompanying files), keep `app/loader.py` + `app/render.py` as the honesty
> core, and deliver in the six stages of §7.
>
> **Acceptance**
> - [ ] `/welcome` → `/ui/chat/` → `/ui/` run without the Jinja legacy
> - [ ] intake collects binary, normal inputs and the crash input
> - [ ] approval binds contract + corpus + binary digests; start is blocked until approved
> - [ ] three audit runs, rubric and `proceed / iterate / change_scope` render from persisted JSON
> - [ ] verdict renders only the six-word vocabulary; `not_run` verbatim; downloads work
> - [ ] no `pipeline.*` imports; honesty tests green; headless walkthrough captured
