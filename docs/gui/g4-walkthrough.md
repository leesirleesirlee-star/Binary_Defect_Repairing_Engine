# G4 end-to-end console demo (M2, 2026-11-23)

The G4 gate asks for the §2 conversation on the real fixture through the
console: upload → analysis → selectable repair contracts → repair → repaired
output.  This document records how the console achieves it and how to reproduce
it.  The console reuses the existing v1.2.2 shell and background/motion code;
only the input, run and output behaviour and their copy changed.

## What the user does

1. Open <http://127.0.0.1:8124/ui/chat/> (fixed URL console).
2. Attach the binary with **添加二进制文件 / Attach binary**
   (`fixtures/stack-overflow-01/vuln.elf` for the frozen fixture demo).
3. Attach the oracle cases with **添加用例文件 / Attach case files**.  Each file
   is a JSON object `{"valid": [...], "invalid": [...]}` (or plain lines; file
   names containing `poc`, `invalid`, `crash` go to the PoC bucket).  The console
   records file names and SHA-256 values; it never executes the uploaded ELF on
   this host.
4. The chat analyses the ELF (`pipeline.analyze`, child process) and shows the
   finding plus **three repair contracts derived from it**:
   - **方案 A · 尾部守卫跳板（推荐）** – redirect the copy call to a guard stub in
     the reserved code tail; valid input ≤ buffer size passes through, invalid
     input gets the fixed error and exit 1.  Implementable in this build.
   - **方案 B · 调用点内联长度检查** – rejected: `insufficient_code_space`
     (moving instructions exceeds the MVP2 edit budget).
   - **方案 C · 入口处提前拒绝超长输入** – rejected: `behaviour_change_risk`
     (changes valid-input behaviour).
5. Select the recommended contract with **选择此修复契约 / Select this contract**.
   The console then, without further clicks: approves the frozen binding
   (`review_binding_digest`), persists the G2 `proceed` decision
   (`{decision, decided_at, binding_digest}` in the task snapshot), stages M3's
   guest observations, and starts the real runner
   (`collect → freeze → analyze → repair → verify`).
6. The final assistant message renders the persisted `VerdictV1` word
   (`verified_against_stated_criteria`) and three downloads:
   `candidate.elf`, `edit-manifest.json`, `verdict.json`.  Nothing in the chat
   computes or edits the verdict.

## What is real in the demo

- The repair starts from the signed G2 plan (`docs/audit/fix-plan-v1.json`) and
  applies it to the frozen fixture (`705ab929…`) — the same path M5/M3 signed.
- Repair and verify run through the merged runner (#48/#52) as child processes;
  the console does not import a pipeline module and does not execute the ELF.
- Verify uses M3's frozen guest observation file
  (`docs/plan/evidence/g3/observations-candidate-wsl2.json`, hash `bb02d3d6…`);
  candidate identity is `c010c006…`, the signed G3 candidate.
- The persisted verdict hash matches the G3 record
  (`51f29be5…` canonical hash) and the criterion table reports 9/9 coverage.

## Honest limits

- The deterministic patcher in MVP2 only applies signed plans to the frozen
  fixture; uploading a different ELF is analyzed (finding/contracts are shown)
  but the console refuses to write a patch with
  `unsupported_binary_scope`.  That is a refusal, not a fabricated success.
- The uploaded oracle cases are recorded as part of the task evidence; the
  MVP2 verifier compares the candidate against the frozen contract/corpus and
  M3's guest observations.  Arbitrary on-host case execution is out of scope and
  stays in the guest.
- The demo's run ends `failed` in `run_end` only because the `export` stage is
  still `stage_not_wired` (honest terminal record); the persisted verdict and
  artifacts are complete and downloadable, and the console renders only the
  persisted verdict.

## Captured evidence

Screenshots (headless Chrome, 1440×900, zh-Hans):

- `screenshots/g4-plan-options.png` — analysis summary + three contracts, one
  implementable.
- `screenshots/g4-repaired-output.png` — verdict `verified_against_stated_criteria`
  and the three download entries.

Automated checks for this change:

```text
$ python -m ruff check .
All checks passed!
$ python -m pytest -q
all host tests passed (5 new G4 tests: upload/analysis/contracts, end-to-end
repair+verdict+download, refused contracts, unsupported binary, upload validation)
$ python scripts/check_modules.py --base origin/main --labels "module:gui,type:feat"
OK: every changed file matches the declared module
```

## Files changed

- backend: `app/g4.py` (upload store, analysis child process, contract
  derivation, task persistence), `app/api.py` (`/api/tasks/upload`,
  `/api/tasks/{id}/g4`, `/api/tasks/{id}/g4/select`).
- console: `app/static/ui/chat/chat-task.mjs` (the upload/select/repair engine),
  `chat-app.mjs` (binary + case-file inputs, auto-start), `chat-view.mjs`
  (contract choice rows, download links), `chat-copy.mjs`, `chat.css`.
- tests/docs: `tests/app/test_g4.py`, this walkthrough, two screenshots.
