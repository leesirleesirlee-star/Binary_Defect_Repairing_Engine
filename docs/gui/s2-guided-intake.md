# S2 guided intake — frozen G1 fixture

Status: implemented on `m2/gui-console-s1` (S1+S2), 2026-11-20.

## Surface

The chat hero gains a small `S2 · 冻结样例已就绪` card. It opens a read-only
review dialog with:

- frozen binary identity (`vuln.elf`, SHA-256, size, ELF facts, entry, reserved R-X tail)
- defect description, five normal inputs, invalid inputs, and the crash/PoC input
- `CaseSetV1` summary and `cases_sha256`
- frozen `ContractV1`, including `stated_criteria`, the flagged diagnostic
  hypothesis, and allowed-edit boundaries
- approval binding `{revision, contract_sha256, corpus_sha256, binary_sha256}`
- approve / deny, plus an explicit frozen-contract edit attempt that returns 409

Start remains disabled: the S3 runner does not exist yet. The dialog never shows a
verdict, pass rate or success label.

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
