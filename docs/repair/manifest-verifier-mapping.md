# Manifest to M3 verifier mapping

Status: **interface reference only**. This document does not replace M3's
verifier, does not define the verdict vocabulary and must not be treated as an
acceptance rule.

M5 writes a dry-run manifest; M3 must independently parse the candidate (or its
observations), recompute every check, and write the verdict. The manifest is
untrusted input to that process.

## Field mapping

| Manifest field | Suggested verifier use | Independence note |
|---|---|---|
| `original.sha256` / `original.size` | Identify the original fixture; reject a mismatch before comparing results | Verifier must hash the original itself |
| `preview.candidate_sha256_if_applied` | Cross-check the expected candidate hash after M5 applies edits | This is a hash, not a candidate file; verifier must hash the actual bytes it receives |
| `edits[].file_offset` | Locate the expected change site | Verifier must confirm the offset is inside the approved range |
| `edits[].vaddr` | Cross-check address/offset mapping | Verifier must not trust the manifest's mapping |
| `edits[].original_bytes` | Preimage check | Verifier must read the original bytes itself |
| `edits[].patch_bytes` | Diff check | Verifier must compute the actual candidate diff |
| `patch_site.original_bytes` / `patch_bytes` | Confirm the 5-byte redirect and call target | Verifier must validate the call site is in R-X and in the approved plan |
| `cave.vaddr` / `cave.file_offset` / `cave.total_size` | Confirm the guard lies in the approved reserved range | Verifier must independently check zero-fill, alignment and range bounds |
| `trampoline.blob` / `blob_sha256` | Expected guard bytes/hash | Verifier must compare actual candidate bytes, not the manifest's claimed hash |
| `invariants.headers_sha256_before/after` | Reference values for header identity | Verifier must recompute headers from original and candidate |
| `invariants.pt_load_count_*`, `pt_load_flags_*` | Reference values for segment invariants | Verifier must parse both ELFs itself |
| `invariants.dynamic_sha256_*` | Reference for no-new-import checks | Verifier must reparse `.dynamic` |
| `invariants.changed_bytes_covered` | Claim that all changes are in edits | Verifier must compute the full byte diff independently |
| `reversibility.restored_sha256` | Claim that inverse edits restore original | Verifier should independently reverse or reapply the edits |
| `manifest_sha256` | Integrity of the manifest payload (excludes `created_at`, the hash itself, and local paths) | Not a candidate hash; verifier must not use it as a verdict input |
| `verdict` | Always `null` | M3 is the only verdict writer; ignore non-null values as a defect |

## What M3 must not accept from M5

- a non-null `verdict`;
- a candidate that does not match its actual bytes;
- an edit outside `patch_site` + reserved range;
- a manifest that claims headers unchanged without an independent comparison;
- a `preview` hash as a substitute for executing the candidate in the guest.

## Suggested independent checks

1. Hash the original; compare with the frozen fixture hash.
2. Parse the candidate; compare ELF/program/section headers and entry.
3. Confirm PT_LOAD count/flags, no W+X and no new imports.
4. Compute the full byte diff; every changed byte must be in the approved edit
   ranges and match the expected patch bytes.
5. Run the candidate in the guest; compare observations with the frozen
   contract/corpus; write `verdict.json` only there.
6. Optionally reverse the edits and confirm the original hash, but do not accept
   M5's reversibility claim without recomputing it.

## Vocabulary

M5 uses structural statuses such as `checks_passed`, `dry_run_checks_passed`,
`no_candidate`, `unsupported`, `dry_run_checks_failed` and `error`. None of these
is a verdict. The only verdict vocabulary is M3/M1-owned.
