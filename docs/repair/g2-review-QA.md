# G2 review Q&A (M5 dry-run)

Status: **pre-G2 written answers, not an approval and not a verdict**. Every
answer below is limited to what the current code/tests actually demonstrate.
The new fixture did not exist when this was written; address-dependent answers
are marked as unverified.

## Q1. How is ABI compatibility on the valid path guaranteed?

**Conclusion.** The valid path is a tail jump to the original `strcpy@plt`.
The guard does not push/call, does not adjust `rsp`, does not write `rdi`/`rsi`,
and leaves the redirecting `call`'s return address untouched. `rax` is the scan
index before the jump, but the original `strcpy` overwrites `rax` with its return
value; no callee-saved register is touched.

**Evidence.**

- `pipeline/repair/guard.py`: valid path `jmp rel32` at code offset 64; the scan
  uses only `rax` as an index and does not touch `rcx`, `rdx` or the stack;
  reject path uses `rdi/rsi/rdx` and never returns.
- `docs/repair/guard-abi.md` sections 3 and 4: instruction table, register and
  stack argument.
- `tests/repair/test_guard.py::test_guard_valid_path_jumps_to_strcpy_plt`
  verifies the tail jump displacement.
- `tests/repair/test_guard.py::test_guard_length_check_opcodes` and
  `test_guard_reject_path_opcodes` verify the exact opcodes and branch targets.
- `tests/repair/test_guard.py::test_guard_shape_and_frozen_message` verifies
  69 code + 42 data and the exact message.

**Not verified.** Runtime behavior, CET/shadow-stack policy, and the real
`strcpy@plt` address. These require the new fixture and M3's guest.

## Q2. How are reversibility and determinism demonstrated?

**Conclusion.** Reversibility is tested for patch sites at the start, middle and
end of `.text`: inverse edits restore the original SHA-256 exactly. Determinism
is tested by building the same manifest twice: the canonical hash and JSON bytes
are identical; `created_at` is excluded from the canonical hash.

**Evidence.**

- `tests/repair/test_negatives.py::test_reversibility_across_patch_sites` covers
  `0x401010`, `0x401194`, `0x40120C` and asserts
  `reversibility.restored_sha256 == original.sha256`.
- `tests/repair/test_negatives.py::test_manifest_is_deterministic` compares
  `manifest_sha256` and written JSON bytes across two runs.
- `tests/repair/test_negatives.py::test_manifest_hash_ignores_created_at`
  proves the optional timestamp does not change the canonical hash.
- `tests/repair/test_negatives.py::test_manifest_hash_is_path_independent`
  proves two different local paths with identical bytes produce the same hash.
- `tests/repair/test_golden_manifest.py` compares the manifest against
  `tests/repair/golden/manifest-cases.json`; the test never rewrites the
  snapshot.
- `pipeline/repair/canonical.py::manifest_sha256` excludes `created_at`, the
  hash field itself, and local path metadata, then sorts JSON keys with compact
  separators.

**Not verified.** Reversibility on the real fixture bytes; the synthetic ELF is
not the frozen fixture.

## Q3. What happens on each abnormal input?

**Conclusion.** The tools stop and return a named non-success status; they do not
patch around a mismatch. Status mapping is:

| Condition | Tool result | Evidence |
|---|---|---|
| Reserved range is not in an R-X/file-backed segment | `unsupported` | `cave_finder` raises `CaveFinderError`; `test_negatives.py::test_no_reserved_tail_is_unsupported`; `validate_fixture` stage `cave_finder` |
| Range has no zero run meeting `min_size`/alignment | `no_candidate` + `max_zero_run` | `test_negatives.py::test_validate_fixture_reports_no_candidate_with_max_run`; `cave_finder.largest_zero_run` |
| Patch-site bytes are not the expected `E8` call | `error` + measured bytes | `test_negatives.py::test_validate_fixture_reports_patch_preimage_error`; `test_patch_writer.py::test_rejects_site_without_call_opcode` |
| Patch-site bytes differ from a caller-supplied preimage | `error` | `test_patch_writer.py::test_rejects_wrong_site_bytes` |
| rel32 cannot reach the cave | `unsupported` + offset | `test_negatives.py::test_rel32_branch_out_of_range`; `validate_fixture` stage `rel32_reachability` |
| Guard does not fit before segment/limit | `no_candidate` | `test_negatives.py::test_guard_overruns_segment`; `test_patch_writer.py::test_rejects_cave_beyond_limit` |
| Self-check invariant fails | `dry_run_checks_failed` | `self_check.py`; `test_self_check.py::test_detects_tampered_patch_bytes` etc. |
| Malformed ELF (truncated header/table, bad machine, huge counts, bad segment range) | `error` | `test_malformed_elf.py`; parser raises `ELFError` and no manifest is written |

**Not verified.** A runtime `write` failure is not observable without M3's guest;
the guard exits 1 on `write <= 0`, and M3 must reject the candidate if stderr is
not exact.

## Q4. Which structural invariants are checked?

**Conclusion.** The manifest and self-check verify header/entry/segment
invariants, dynamic-section stability, byte accounting and reversibility. They
are structural checks only; they do not decide whether the candidate is correct.

**Evidence.**

| Invariant | Where checked |
|---|---|
| ELF/program/section headers byte-identical | `patch_writer._invariants`; `self_check` `headers_unchanged` |
| Entry point unchanged | `entry_unchanged` |
| PT_LOAD count unchanged | `pt_load_count_unchanged` / `no_new_segments` |
| PT_LOAD permissions unchanged, no W+X | `pt_load_flags_unchanged`, `no_wx_segments` |
| `.dynamic` unchanged / no new imports | `dynamic_section_unchanged`, `no_new_imports` |
| Every changed byte covered by an edit | `changed_bytes_covered` |
| Inverse edits restore original hash | `reversibility`, `restored_sha256_matches` |
| Manifest itself not altered | `manifest_sha256_matches` |

Tests: `tests/repair/test_patch_writer.py::test_manifest_invariants_are_structural_only`,
`tests/repair/test_self_check.py` and `tests/repair/test_negatives.py`.

## Q5. Which assumptions remain unverified?

1. The real fixture hash, patch-site address, reserved range and `strcpy@plt`
   address. All are example values only.
2. Runtime behavior in the guest, including exact stderr and exit code.
3. NUL-termination of the argv string; the guard scans at most 32 bytes.
4. CET/shadow-stack and signal behavior during `write`.
5. The frozen `EditManifestV1` field names and verifier's independent range
   accounting.
6. The product fallback when no cave exists: current contract forbids segment
   extension, so M5 returns `no_candidate`; a future ADR is required.

**Required M3 coverage.** Run the candidate in the disposable guest, produce
observations, and let `pipeline/verify` decide. M5 does not execute the ELF and
does not write a verdict.

## Evidence summary

```text
pytest tests/repair                 79 passed
pytest -q -m "not guest"            108 passed
ruff check .                        All checks passed (ruff 0.17.6)
```

The counts and test names above are the current branch state; they are not a
substitute for the new-fixture preflight.
