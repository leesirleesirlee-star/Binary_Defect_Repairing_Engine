# Static console shell (S1)

Install the shell-only runtime dependencies (M1 owns the root requirements file):

```bash
pip install 'fastapi>=0.115,<1' 'uvicorn>=0.30,<1'
```

Run the copied v1.2.2 welcome/chat/archive surfaces unchanged:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8124
```

- <http://127.0.0.1:8124/welcome>
- <http://127.0.0.1:8124/ui/chat/?preview=1>
- <http://127.0.0.1:8124/ui/>

S2 guided intake is included: `/api/fixture` exposes the frozen G1 fixture for
display; the chat hero creates a task, approves the task binding and enables
Start. The frozen contract remains read-only.

## S3+ API and event journal

`GET /api/session`, `/api/tasks`, approval, decision, Start/cancel, SSE replay,
analysis/artifact reads and export are implemented. Start spawns the M1 runner
`scripts/run_task.py`; the runner executes the available `pipeline.analyze`
stage and reports not-yet-wired audit/decision/repair/verify/export stages as
`stage_not_wired`. It never fabricates a verdict or success. The GUI never
imports pipeline modules.

See [`docs/interfaces/gui-events-v1.md`](../docs/interfaces/gui-events-v1.md),
[`docs/gui/s3-api-events.md`](../docs/gui/s3-api-events.md) and
[`docs/gui/s2-guided-intake.md`](../docs/gui/s2-guided-intake.md).

## Reference v1.2.2 GUI (switchable)

The reference GUI can run beside this console and is reachable at any time from
`/legacy` (welcome header, welcome shortcuts, chat rail footer and Settings →
About). Start it once in another terminal:

```bash
./scripts/start-legacy-gui.sh    # http://127.0.0.1:8125, shares this console's session token
```

- `BINARYREPAIR_LEGACY_DIR` points at the reference checkout (default: the
  Desktop copy), `BINARYREPAIR_LEGACY_PORT` changes the port.
- `BINARYREPAIR_LEGACY_URL` tells the console where the reference GUI listens;
  both apps share the same `br_session` token so the session survives the switch.
- The reference app links back to `/welcome` from its top nav, sidebar and a
  floating button. If it is not running, `/legacy` renders a short page with the
  start command instead of a dead redirect.
