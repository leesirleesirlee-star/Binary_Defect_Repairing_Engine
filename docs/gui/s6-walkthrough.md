# S6 headless walkthrough and current evidence

Status: partial, 2026-11-20. The console can be exercised end-to-end for the
frozen fixture through **real analysis**; audit/repair/verify remain blocked by
open mainline PRs (#36 audit, #28 repair, #11 verify).

## Walkthrough

1. Start the shell:

   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8124
   ```

2. Open <http://127.0.0.1:8124/ui/chat/?preview=1>.
3. Click **审阅语料与契约**; the frozen fixture, five valid inputs, four invalid
   inputs, PoC, and the frozen ContractV1 are read-only.
4. Click **批准契约**. A task is created and approved against
   `{revision, contract_sha256, corpus_sha256, binary_sha256}`.
5. Click **开始修复**. Start requires the CSRF token and an idempotency key and
   spawns `scripts/run_task.py`.
6. The event console shows the real `plan_update`, `command` and `file_change`
   events. Analysis artifacts `disassembly.json` and `finding.json` are fetched
   from `/api/tasks/{id}/analysis` and are downloadable.
7. The runner then reports `stage_not_wired` for audit/decision/repair/verify/
   export and terminates with `run_end.execution = failed`. No verdict or success
   is fabricated.
8. `/ui/` shows the S6 archive bridge: task list, export JSON, and event console.

## Captured evidence

- `docs/gui/screenshots/s6-archive.png`
- `docs/gui/screenshots/s6-preview-cards.png`
- `docs/gui/screenshots/s2-real-analysis.png`

## Honest limitations

- S3 preview cards (`audit_runs`, decision, manifest diff, not_run checks) are
  labelled `合成预览`; they do not satisfy G2/G3 acceptance.
- S4 cannot render real three-run audit rows until #36 lands.
- S5 cannot render an applied manifest or persisted VerdictV1 until #28/#11 land.
- S6 download of repaired ELF/verdict/audit requires those artifacts; only real
  analysis artifacts exist today.

## Commands verified

```text
pytest tests/app -> 48 passed
ruff check . -> All checks passed
GET /api/tasks/{id}/analysis -> available: true after real analysis
GET /api/artifacts/{id}/download -> 200 for disassembly.json/finding.json
```
