# G4 gate record — the console deliverable and its evidence

- **Gate:** G4 (GUI + delivery)
- **Date:** 2026-11-24 (Asia/Shanghai)
- **Signed by:** M1 `@leesirleesirlee-star`
- **Commit under verification:** `6b96020` (`main`: console #56, AI-hosted chat #73, runner live mode #75, live-AI contract #69/#74, WSL2 driver #72, G4 runner export #57)
- **Tag:** `v0.1.0` (annotated tag on this record's squash merge commit)
- **Walkthrough:** `docs/gui/g4-walkthrough.md`; screenshots under `docs/gui/screenshots/`

## 1. What G4 delivers

A minimal chat-first console at a fixed URL over the existing v1.2.2 shell:

```text
/welcome -> /ui/chat/ (console) -> /ui/ (archive, live G1-4 task store)
```

The conversation uploads the frozen fixture and its case files, shows the
deterministic analysis, offers the three repair contracts derived from the
finding, binds the signed G2 decision when one is selected, runs
`scripts/run_task.py` (analyze -> decision -> repair -> verify -> export), and
renders the persisted `VerdictV1` with downloads. The right-side pane carries the
signed G2 record, the runner's eight-step checklist and the chronological journal.

## 2. Acceptance (START-HERE section 7, G4)

| Item | Status | Evidence |
|---|---|---|
| `/welcome -> /ui/chat/ -> /ui/` open without the Jinja legacy | met | routes in `app/main.py`; live check of all three pages |
| conversation is AI-hosted (LLM assistant + deterministic fallback + honest badge) | met, scoped | `app/assistant_client.py` -> `app.api.ASSISTANT_CLIENT`; follow-up turns call `POST /api/tasks/{id}/assistant`; badge `AI 助手 · llm` / `确定性回退` / `AI 未接线` (#73). The guided intake/progress lines stay deterministic by design; free-form turns are model-hosted. |
| chat collects the binary, normal inputs, crash input, then freezes the contract | met, scoped | the upload flow records binary + case files; the contract is the G1-frozen `contract.json` (frozen before AI, by design) and the console binds it rather than re-authoring it |
| approval binds contract + corpus + binary digests; Start blocked until approved; Start runs `scripts/run_task.py` | met | `review_binding_digest` recomputed and enforced by the API and the runner (#51/#53/#52/#48) |
| three-run audit, decision, patch/verdict narrated; score cards hidden; right-side panels live | met | G2 record narrated ("3 次审计 … 决策 proceed"); right-side journal-polled monitor: 8 chips, `审计 已跳过 · satisfied_by_signed_g2`, 32 events, one current run card; no reload needed (#56) |
| verdict uses only the six-word vocabulary; `not_run` verbatim; downloads resolve | met | persisted `verdict.json` rendered verbatim; `candidate.elf` / `edit-manifest.json` / `verdict.json` downloads return the hash-bound bytes |
| no `pipeline.*` import in `app/`; honesty tests green; headless walkthrough; `v0.1.0` tagged | met | grep and `tests/app` honesty suite; walkthrough + screenshots; tag on this record |

## 3. End-to-end demo (signed replay)

Commands used on the verification host (Windows; headless Chromium for the
screenshots):

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 8124
open http://127.0.0.1:8124/welcome
```

Observed on `main` at `6b96020` (one-click demo, zh-Hans):

- header `步骤 7 / 8`, `已结束 · completed`;
- conversation: analysis summary, signed-G2 narration, contract A
  ("G2 已批准计划的策略"), bound decision, `修复运行` 7/8 card, verdict
  `verified_against_stated_criteria`, three downloads;
- right panel: signed G2 rows, eight-step checklist (`审计 已跳过`), 32 journal
  records, one current run;
- artifacts: `candidate.elf` `c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28`,
  `verdict.json` canonical `51f29be55aea38070029429b1102eb7a0ee1557dbf99b15cdce64440e5bec45c`,
  `export/bundle-manifest.json`.

The AI-hosted assistant was exercised without a key on this host: badge
`确定性回退`, follow-up answered from persisted facts with no invented numbers.
The keyed `llm` path was exercised by M2 (#73: header `AI 助手 · llm`, screenshot
`g4-ai-chat.png`) and is covered by the injected fake-client tests.

## 4. Checks

```text
$ ruff check .                       All checks passed!
$ pytest -q -m "not guest"            2 known Windows-only failures:
                                      test_loader.py::test_symlink_escape_is_rejected
                                      test_assistant_key.py::test_save_masks_and_never_echoes_the_key
                                      (symlink privilege / POSIX mode; both green on Linux CI)
$ python scripts/check_modules.py --base origin/main   OK
```

CI on the merged heads: #56 `test` + `modules` green; #73 `test` + `modules`
green; #75/#72/#74 green. The console demo itself runs `run_task.py` as a child
process; the host never executes an ELF.

## 5. Honest limits

- **Replay, not a live audit or guest.** G4 replays the signed G2 three-run audit
  and M3's recorded WSL2 observations; the host executes no ELF. The additive
  live audit + live guest chain is G4.1 (#68), not part of this gate.
- **Uploaded cases are task evidence only.** Verification uses the frozen corpus
  and M3's guest observations; the host never runs the uploaded ELF.
- **Only the frozen fixture is patchable.** Other ELFs are analyzed read-only and
  refused, never fabricated.
- **V4 static recognition is pattern-based**; an unrecognized guard layout would
  be `unverified`, never a pass.
- **The G3 guest was a fresh-boot WSL2 VM**; strict disposable-VM isolation is an
  open limitation carried from G3.
- **AI hosting is scoped**: free-form turns are model-hosted; the guided flow
  narration is deterministic.
- Two Windows-only tests fail locally (symlink privilege, POSIX mode); CI is
  Ubuntu and green.

## 6. Decision

**G4 is accepted.** The console delivers the conversation, the eight-step run with
the signed G2 binding, the persisted verdict, the live journal panels and the
downloads, with the AI assistant wired and its mode badge truthful. Tag
`v0.1.0` on this record's squash merge commit.

The next increment, **G4.1** (live three-run audit + live WSL2 guest verification),
is tracked in #68; it is additive and does not change this record, the frozen
contract/corpus or the verdict rules.
