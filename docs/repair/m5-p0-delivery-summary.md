# M5 P0 delivery summary (dry-run)

Status: **P0 tooling / G0 preparation**. This is not a repair result, not a
candidate and not a verdict. PR #19 is open; PR #14 and the new fixture are still
pending.

## 1. Tool modules

Seven core tool modules plus two support modules, all pure Python standard
library:

| File | Role |
|---|---|
| `pipeline/repair/elf64.py` | ELF64 header/segment/section/relocation parser, vaddr↔file map, dry-run edits |
| `pipeline/repair/cave_finder.py` | explicit-range and all-R-X cave scan, alignment/overlap/rel32 checks |
| `pipeline/repair/guard.py` | 69-byte x86-64 guard + 42-byte frozen message |
| `pipeline/repair/patch_writer.py` | dry-run manifest writer; never writes a candidate |
| `pipeline/repair/self_check.py` | structural invariant check; not a verdict |
| `pipeline/repair/manifest_schema.py` | provisional shape and future `EditManifestV1` extension slots |
| `pipeline/repair/validate_fixture.py` | one-shot preflight framework for the new fixture |
| `pipeline/repair/canonical.py` | canonical manifest hash shared by writer/self-check |
| `pipeline/repair/__init__.py` | version and CLI exit-code constants |

## 2. Tests

Current local branch:

```text
pytest tests/repair                 91 passed
pytest -q -m "not guest"            177 passed (178 collected; 1 Windows symlink-only failure)
```

Coverage dimensions:

- boundary: exact 111-byte cave, exact INT32_MAX rel32, patch site in last 5
  bytes of R-X;
- malformed: truncated header/phdr/shdr, bad machine, huge counts, bad segment
  range, zero-length R-X, invalid permissions, overlapping PT_LOAD;
- reversibility: start/middle/end patch sites restore the original SHA-256;
- determinism: canonical hash stable across paths/timestamps, golden snapshots;
- guard: exact opcodes, branch offsets, message, 69+42 bytes.

Main now contains PR #19-#25; this branch adds 3 boundary tests and the
`guard-byte-breakdown.md` hardening. The only host failure is the Windows
symlink-permission test, which fails on clean main too.

## 3. Documents

Current `docs/repair/` set (12 files, including this summary):

| Document | Use |
|---|---|
| `dryrun-tools.md` | tool scope, commands, error codes, assumptions |
| `guard-abi.md` | ABI/tail-jump review |
| `guard-byte-breakdown.md` | byte-by-byte guard table and branch arithmetic |
| `m4-handoff-checklist.md` | M4 proposal cross-check |
| `repair-feasibility-note.md` | G2 pre-read: budget, invariants, limits |
| `g2-review-QA.md` | review Q&A with test evidence |
| `preflight-report-template.md` | fixed report structure for the real fixture |
| `fixture-exception-handling.md` | preflight failure handling |
| `pr-submission-checklist.md` | PR/commit/governance checklist |
| `manifest-verifier-mapping.md` | manifest-to-verifier field mapping |
| `pr-review-responses.md` | concise PR #19 responses |
| `m5-p0-delivery-summary.md` | this delivery summary |

## 4. Governance compliance

- All changes are under `pipeline/repair/`, `tests/repair/`, `docs/repair/`.
- No fixture, contract, cases, schema, verifier, app or module registry file was
  modified by M5.
- No `candidate.elf`; every manifest has `dry_run: true`, `verdict: null`,
  `preview.candidate_written: false`.
- No host execution of the fixture or candidate; no `verdict.json`.
- All validation is synthetic; real-fixture preflight waits for PR #14 + M3's
  new fixture.

## 5. Current status

| Item | State |
|---|---|
| PR #19 | merged to `main` as `e634d5d` |
| PR #20 (hardening) | open, separate follow-up; CI running |
| PR #14 / ADR 0001 | merged to `main` as `ae29dd5` |
| M3 new fixture | not published; `main` fixture tree still has only placeholders |
| Real preflight | not_run |
| Candidate | not created |
| Verdict | null (M5 does not write one) |

## 6. Reproduction

```bash
python -m pytest -q tests/repair
python -m pytest -q -m "not guest"
ruff check .
python scripts/check_modules.py --base origin/main --labels "module:repair"
```

The hardening tests/docs are in the separate PR #20. PR #19 is already merged;
the new fixture is still missing, so real-fixture preflight remains `not_run`.
