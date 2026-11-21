# M2 GUI plan — minimal chat-first repair console (Revision 2.2, AI-hosted chat + live run panels)

- **Status:** Revision 2.2 for M2, 2026-11-21 (Asia/Shanghai). Revision 2 (minimal chat-first)
  responded to the Lead review of Revision 1; Revision 2.1 made the chat AI-hosted (LLM assistant
  with a deterministic fallback); Revision 2.2 records a Lead decision on the right-side panels:
  the real-time **修复运行监视 + 事件日志** panels stay in the chat page — users get a live
  progress and event display alongside the minimal chat. Revision 1 text stays in git history.
- **Module:** `gui` (M2). Paths: `app/`, `tests/app/`, `docs/gui/`. Gate: G4, staged with G1–G3.
- **Lead review of Revision 1:** (1) the cards added by Revision 1 make the UI cluttered;
  (2) the process must be controlled through the AI conversation — the user must not see
  corpus/contract review and event-stream details; (3) keep it minimal and AI-chat-first.
- **Reuse source:** unchanged — archived `Binary_Repair` v1.2.2 (`b885d21`) conversation UI shell
  (`app/static/ui/`). Mainline contracts (`ADR 0003`, `docs/interfaces/gui-events-v1.md`, the
  runner `scripts/run_task.py`) are **not** changed by this revision.

## 1. Design principle (Lead decision)

1. **The chat is the only surface.** One thread drives the whole task.
2. **The chat is AI-hosted.** An LLM assistant runs the whole conversation: it asks for the
   binary, the normal inputs and the crash input, narrates progress, answers follow-up questions
   like a normal AI, proposes the next action and ends with the download. The user answers in
   natural language, attaches files, and taps inline action chips. Without a provider key (or on
   any provider failure) the assistant falls back to scripted deterministic lines with an honest
   mode badge — the conversation still completes, it is just not model-generated.
3. **Hidden by default:** corpus JSON, contract JSON, event journal, tool/command rows, the rubric
   table, per-run scores and raw responses. They exist in the backend and in the evidence, and are
   reachable only through one unobtrusive evidence entry and the final download bundle.
4. **Keep the v1.2.2 shell** (layout, CSS, composer, streaming, i18n, a11y). Simplification is done
   by **hiding components**, not by redesigning them.
5. **Gates stay machine-enforced.** The AI hosts the dialogue, not the decisions: the backend
   still refuses to start before approval, the G2 decision still requires the user's chip, and
   only the deterministic verifier writes a verdict. The chat AI proposes; the system and the user
   dispose.
6. **Real-time transparency (Lead decision 2026-11-21).** The chat page keeps the right-side
   panels — **修复运行监视** (phase checklist, status, artifact links) and **事件日志**
   (chronological SSE journal). They do not conflict with the minimal chat: the chat is the
   conversation surface, the panels are the live status surface. Corpus/contract/score cards stay
   hidden; the journal panel is the user-facing real-time display.

## 2. The whole UI is this conversation (MVP2 demo script)

```text
AI   你好。把有问题的程序发给我，并说明它出问题的现象。
U    (附件 vuln.elf) 输入太长会崩溃
AI   已收到 vuln.elf（SHA-256 前 8 位）。请粘贴几个正常输入，以及一个能让它崩溃的输入。
U    正常: 空串 / A / hello / 31个A；崩溃: 64个A
AI   已整理 9 个用例并冻结契约。开始 AI 分析吗？            [开始]
U    (点击 开始)
AI   正在生成反汇编视图… 审计 1/3… 2/3… 3/3
     第 1 次方案得分 86、无严重错误；第 2 次 74；第 3 次 62。
     建议采用第 1 个方案。继续吗？                          [继续] [重跑]
U    (点击 继续)
AI   补丁已生成并写入候选程序。正在验证…
AI   验证完成：verified_against_stated_criteria。
     下载修复后的程序与证据：                               [下载] [证据]
```

That is the conversation surface. Next to it, the right-side panels give the **live** view while a
run is active: 修复运行监视 (phases, status, artifact links) and 事件日志 (chronological journal).
Other UI elements beyond chat text:

- attachment affordance (binary), text paste for inputs, inline action chips, Stop while running,
  the download button on the final message, and the minimal sidebar (new chat / recent / settings).

## 3. What Revision 1 rendered and Revision 2 hides

| Revision 1 element | Revision 2 treatment |
|---|---|
| corpus card, contract card (CaseSetV1 / ContractV1 fields) | one AI line: "已整理 N 个用例并冻结契约（hash 前 8 位）"; full JSON only via 证据 / 下载 |
| `plan_update` checklist, step rows, activity rows | one progress phrase inside the AI message ("审计 2/3…") or the thinking indicator |
| approval card with revision/digest lists | inline chips `[开始] [继续] [重跑]`; the backend still enforces `review_binding_digest` and blocks start until approved — the UI simply shows nothing |
| three-run score table, rubric, `EditManifestV1` diff card | one summarizing sentence; tables/diffs only in 证据 / 下载 |
| tool / command / `file_change` / event rows | never rendered in the chat; the journal stays for the archive and for honesty |
| right execution pane: 修复运行监视 + 事件日志 | **kept and visible** (Lead decision 2026-11-21): live phase checklist, status, artifact links and the chronological SSE journal |

## 4. Assistant: AI-hosted chat with a deterministic fallback (the new M2 component)

- `app/assistant.py` implements the chat assistant: intake questions, progress narration from the
  journal, free-form answers and action chips, emitted as a small validated envelope
  (`{reply, actions[]}`); invalid model output falls back to the scripted reply.
- **Two AIs, one wall between them.** The audit model (fixed prompt, temperature 0, three hashed
  runs — the G2 evidence) and the chat assistant are separate. The chat assistant never writes
  `FixPlanV1`, the audit report or the verdict, never sees source, the hidden corpus, keys or raw
  provider diagnostics, and its text is never evidence.
- **Provider seam (v1.2.2 `assistant_llm` pattern).** M2 implements a `client` seam
  (`chat_json(messages, ...)`) plus a fake transport for tests; M1's infra injects the real
  DeepSeek client, so the key stays in one host process and never reaches `app/` or the browser.
  No client, no key or a failed call → deterministic fallback (`mode: deterministic`, honest
  badge, localized fallback code, no raw provider text).
- Rules (test-locked):
  1. verdict words come verbatim from `VerdictV1.verdict` (six-word vocabulary), nothing else;
  2. a failure is one line with the stable reason code + a 详情 link, never a guess;
  3. no invented numbers: missing tokens/model are simply not mentioned;
  4. mode badge tells the truth (`llm` / `deterministic` / `llm (not wired)`); fallback shows its
     localized code, never raw provider text;
  5. chat text is never evidence and never enters the audit inputs.

## 5. Interface deltas vs Revision 1

- SSE and the event journal are still consumed **internally** to drive the assistant and the
  progress line; the 18 event types and `docs/interfaces/gui-events-v1.md` are unchanged.
- The browser API (§5.1 of Revision 1) is unchanged; the UI simply stops rendering most returned
  fields in the chat.
- The honesty core (`app/loader.py`, `app/render.py`) and the no-`pipeline.*` import rule are
  unchanged. The runner (#38) is unchanged.

## 6. M2 task breakdown (Revision 2, replaces Revision 1 §8)

| Task | Content | Blocks on |
|---|---|---|
| T1 | static shell port; hide plan-checklist / tool-row / approval-card components by default | none |
| T2 | intake Q&A flow: binary attach, normal inputs, crash input, action chips | none |
| T3 | `app/assistant.py` (LLM chat + deterministic fallback + action chips) + progress line + final download message, against a synthetic journal | gui-events-v1 (#37, merged); real client injected by M1 infra |
| T4 | `app/api.py` + SSE reader (Revision 1 T-GUI-4/5 minus the card renderers) | none beyond #37 |
| T5 | evidence link to the archive + honesty tests | #11 merged |
| T6 | demo fixtures, headless Edge walkthrough, screenshots, G4 evidence | T1–T5 |

Each PR stays ≤400 changed lines with one `module:gui` label; no PR imports
`pipeline.verify/repair/ai`.

## 7. Acceptance (Revision 2)

- The §2 conversation reproduces end-to-end on the frozen fixture: attach → inputs → freeze →
  audit → decision → patch → verdict → download.
- **No** corpus/contract/event/score cards are visible in the chat; details are reachable only via
  the evidence entry or the download bundle.
- The verdict renders only the six words from `VerdictV1`; `not_run` and failures stay honest;
  no `pipeline.*` imports; honesty tests green; headless walkthrough captured.
- The assistant completes the §2 conversation in `llm` mode with a key, and in `deterministic`
  mode without one — the badge says which, and the fallback never fabricates model metadata.
- The right-side panels render the run's phases and the event journal **in real time** while the
  chat column stays free of corpus/contract/score cards.

## 8. Mainline notes

- ADR 0003, `docs/interfaces/gui-events-v1.md` and the runner (#37/#38, merged) are unchanged.
- The chat assistant depends on the same DeepSeek key decision as G2 (roadmap §9.4); without it
  the console runs in deterministic mode and still completes the flow.
- PR #39 (roadmap/START-HERE wording) should say "minimal chat-first console" rather than the
  Revision 1 card wording — M1 to adjust before merging #39.
- Issue #12 acceptance items that mention corpus/contract cards are dropped (Appendix A).

## Appendix A — updated acceptance body for issue #12

> **Title:** Minimal chat-first repair console (reuse the v1.2.2 chat UI)
>
> One chat thread drives the roadmap path: the AI asks for the binary, normal inputs and the crash
> input, narrates progress, asks for confirmations, and ends with the download of the repaired ELF
> and its evidence. Corpus/contract/events/score details are hidden from the chat and live only in
> the evidence entry and the download bundle. See
> [`docs/gui/conversation-console-plan.md`](conversation-console-plan.md) Revision 2.
>
> **Acceptance**
> - [ ] the §2 conversation reproduces end-to-end on the frozen fixture
> - [ ] the chat is AI-hosted with an honest deterministic fallback (badge, no fake metadata)
> - [ ] no corpus/contract/event/score cards in the chat
> - [ ] verdict renders only the six-word vocabulary; `not_run` verbatim
> - [ ] no `pipeline.*` imports; honesty tests green; headless walkthrough captured
