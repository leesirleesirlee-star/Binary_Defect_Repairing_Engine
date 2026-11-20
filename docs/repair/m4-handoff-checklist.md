# M4 handoff cross-check (M5 dry-run)

Source: M4 `M5-repair-handoff-reserved-rx-tail-2026-11-20.md`.
Status: **pre-G2 self-check, not an approval and not a verdict**. The addresses
below are synthetic/example values until M3 publishes the new fixture hash.

Legend: ✅ aligned in code/docs; ⚠️ must be revalidated on the new fixture;
❌ intentionally not implemented by M5 in this phase.

| # | M4 item | M5 status | Evidence / note |
|---:|---|---|---|
| 1 | Accept ADR 0001 option B: reserve the R-X tail at build time | ✅ | M5 does not edit program headers; manifest requires headers unchanged. |
| 2 | Candidate keeps program/section headers byte-identical | ✅ | `patch_writer` invariant + `self_check` header comparison; test `headers_unchanged`. |
| 3 | Redirect one eligible 5-byte `call strcpy@plt` | ✅ | `patch_writer` checks `E8`, preimage, executable segment, rel32; emits `e8 + rel32`. |
| 4 | Guard scans source bytes 0..31 for NUL | ✅ | `guard.py` bytes `31 c0 80 3c 06 00 74 38 ff c0 83 f8 20 72 f3`. |
| 5 | Valid path tail-jumps to original `strcpy@plt` | ✅ | `jmp rel32` at guard offset 64; `rdi`/`rsi`/return address untouched. |
| 6 | Reject path writes exact 42-byte stderr and exits 1 | ✅ | `write(2, msg, 42)` loop + `exit_group(1)`; `ERROR_MESSAGE` frozen. |
| 7 | No new PT_LOAD, no new import, no W+X | ✅ | `pt_load_count`, flags, `.dynamic`, no-W+X checks; no header edits. |
| 8 | Guard/data budget | ✅ | 69 code + 42 data = 111 bytes; limits 256/64. |
| 9 | Full byte-level reversibility via manifest | ✅ | inverse edits restore original SHA-256; tested at start/middle/end patch sites. |
| 10 | Manifest records every offset/vaddr/original/patch/purpose | ✅ | `edits[]`, `patch_site`, `cave`, `trampoline`, `invariants`, `reversibility`. |
| 11 | M5 does not write a verdict | ✅ | `verdict: null`, `verdict_written_by_m5: false`; no `pipeline/verify` import. |
| 12 | M5 does not execute the candidate/guest | ❌ by rule | No execution in code/tests; M3 owns guest verification. |
| 13 | M5 does not modify the real fixture | ❌ by rule | Dry-run only; no `candidate.elf`, no fixture writes. |
| 14 | Patch-site address `0x401194` | ⚠️ | Example only; re-measure on new fixture. |
| 15 | Reserved range `0x401211-0x402000` | ⚠️ | Example only; read new manifest/headers; 16-byte alignment yields `0x401220`. |
| 16 | `strcpy@plt` address `0x401060` | ⚠️ | Example only; approved plan must provide the real target. |
| 17 | Jump displacements / call rel32 | ⚠️ | Recompute on new hash; `encode_rel32_branch` rejects out-of-range. |
| 18 | Contract semantics (31-byte valid, 32-byte reject, exact stderr) | ⚠️ | M5 does not define it; must match M1 frozen `ContractV1`. |
| 19 | Cave finder is a product component, not "reserved-only" | ✅ interface | `find_caves_in_segments()` scans every file-backed R-X segment; explicit-range mode remains for fixture preflight. |
| 20 | Segment extension fallback if no cave | ❌ out of scope now | Current contract/ADR forbids it; not implemented or silently attempted. Requires a future ADR and agent-produced safety proof. |

## Relevant open questions

- Will the new fixture's reserved range still start at `0x401211`, and is
  `0x401220` acceptable as the 16-byte-aligned guard start?
- Which exact `EditManifestV1` field names does M1 freeze?
- Does M3's verifier independently enforce allowed ranges and byte accounting?
- What is the approved behavior for non-printable argv values and unavailable
  stderr?

## Explicit non-claims

A `checks_passed` self-check or `dry_run_checks_passed` preflight is **not** a
repair verdict. It only means the manifest is structurally applicable. M3 must
run the guest and write the verdict.
