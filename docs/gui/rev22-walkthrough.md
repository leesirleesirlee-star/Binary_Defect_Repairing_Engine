# Rev 2.2 headless walkthrough (M2 / #12)

Captured 2026-11-22 with the fixed-URL console at `http://127.0.0.1:8124/ui/chat/`,
Chrome headless `1440x900`, dark theme, reduced motion off. The console runs the
deterministic assistant fallback (`app/assistant.py` mode `deterministic`); the
live provider client is injected by M1's host infrastructure.

## Steps

1. Open `/ui/chat/` — the empty conversation shows the composer, the attachment
   affordance **添加二进制文件 / Attach binary** and the sample-contract shortcut.
   The right-side panel is the compact pre-run shape (`执行详情 / Execution` with
   the repair-progress strip and a `详情` expander).
2. Choose a binary with the attachment control. The upload-only flow sends the
   intake turn, freezes the synthetic contract, records the approval decision and
   starts the repair without further chat text or clicks.
3. During the run the right-side panel expands to the live surface
   (`运行概览 / Run overview`, `路线 A/B`, the run monitor and `事件日志 / Event log`).
4. The run ends with the honest verdict line: `尚无结论（…）；详情：…` — the
   deterministic demo never fabricates a verdict or a passed check.

## Observed DOM assertions (headless)

| Check | Observed |
|---|---|
| chat column cards (`.approval`, `.summary-card`, `.step-card`) | `0` |
| inline action chips in chat | approve/deny are gone; upload drives the flow |
| right panel visible while a run is active | `execution-scroll` `display: block`; route monitor cards rendered |
| verdict vocabulary | only persisted `VerdictV1` words; missing verdict renders the reason code + details link |
| mode badge | `deterministic` (no provider client wired) |

Screenshots:

- `screenshots/rev22-minimal-chat.png` — minimal chat column, right panel visible.
- `screenshots/rev22-upload-only-flow.png` — upload-only run: frozen contract,
  automatic approval, live right-side panels, honest final line.

## Reproduce

```bash
# from the repo root, with the test environment's Python
python -m uvicorn app.main:app --host 127.0.0.1 --port 8124
# then open http://127.0.0.1:8124/ui/chat/ and attach any local file
```

Automated checks used for this PR:

```text
$ python -m ruff check .
All checks passed!
$ python -m pytest -q
318 passed
$ python scripts/check_modules.py --base origin/main --labels "module:integration,type:feat"
OK: every changed file matches the declared module
```

## Limits

- This branch reuses the Revision-1 shell; T1/T2/T4/T5/T6 are implemented on it,
  T3 (`app/assistant.py`) landed in the last commit.
- End-to-end verdict on the frozen fixture still depends on the runner wiring
  (#48, M1) and the verifier merge (#47); the GUI only renders persisted
  `VerdictV1`/journal values.
- The browser API endpoint `POST /api/tasks/{id}/assistant` is wired and tested;
  the current UI keeps its local deterministic engine until T4's live SSE loop is
  merged, and the badge is truthful either way.
