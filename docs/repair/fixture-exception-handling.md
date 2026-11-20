# New fixture exception handling

Status: **dry-run preflight procedure**, effective only after M3 publishes the
fixture with ADR 0001's reserved tail and M1 has frozen the owning contract.
This procedure must not be used to relax a check or to make a fixture fit.

## Hard rules

1. Do not edit the fixture, contract, cases, manifest or headers to make the
   preflight pass.
2. Do not enable segment extension or add a `PT_LOAD` when no cave is found.
3. Do not change the error string, input limit or exit code.
4. Do not write a candidate or a verdict while handling an exception.
5. Report the measured value, not an assumed one.

## Status table

| Exception | Preflight status | Action | Report to |
|---|---|---|---|
| Reserved range is not in an R-X/file-backed segment | `unsupported` | Stop. Print the measured segment/range mismatch. Do not move the range. | M1/M3 |
| No zero run meets `min_size` and 16-byte alignment | `no_candidate` | Stop. Print `max_zero_run` and the requested `min_size`. Do not enable segment extension. | M1/M4 |
| Patch-site original bytes do not match the expected `E8` call | `error` | Stop. Print the measured 5 bytes. Do not guess another call site. | M4 |
| rel32 cannot reach the cave | `unsupported` | Stop. Print the actual signed displacement. Do not relocate the cave silently. | M4 |
| Self-check structural invariant fails | `dry_run_checks_failed` | Stop. Print every failed check and its detail. Do not suppress a failed check. | M1 |
| Manifest write/IO failure | `error` | Stop. No candidate is written; report the path error. | M1 |
| ELF parse failure / unsupported class, machine or type | `error` | Stop. Print the parser detail. Do not attempt a different parser. | M1/M3 |
| Patch writer rejects an unsafe cave (non-zero, overlap, header) | `unsupported` | Stop. Report the exact safety failure. Do not zero-fill or relocate automatically. | M1/M4 |
| Writer cannot fit guard before segment/limit | `no_candidate` | Stop. Report required bytes vs available bytes. Do not shrink the guard or change the message. | M4 |

`no_candidate` is a structural availability result, not a verdict. A product
fallback would need a future ADR for segment extension and an agent-produced
safety proof; it is out of scope for this preflight.

## Where each status comes from

- `parse_elf`: `ELF64.from_path` / `ELFError`.
- `patch_site_preimage`: `ELF64.read_vaddr`, executable-segment check, `E8`
  opcode check.
- `cave_finder`: `cave_finder.find_caves` / `CaveFinderError`;
  `largest_zero_run` for the no-candidate detail.
- `rel32_reachability`: `elf64.fits_rel32(patch_site + 5, cave_vaddr)`.
- `patch_manifest`: `patch_writer.build_manifest` / `PatchWriterError`.
- `self_check`: `self_check.check_manifest` status.
- `write_manifest`: JSON output only; never a binary.

## Exit codes

| Status | CLI exit |
|---|---:|
| `dry_run_checks_passed` | 0 |
| `no_candidate` | 1 |
| `unsupported` | 1 |
| `dry_run_checks_failed` | 1 |
| `error` | 2 |

## Evidence to attach

For every failed preflight attach:

- fixture path and SHA-256;
- requested start/end, patch site, `strcpy@plt`, `min_size`;
- full JSON report (`validate_fixture --out`);
- measured values (max zero run, actual patch bytes, rel32 displacement);
- the exact tool version (`--version`) and command line.

Never attach a candidate or a verdict; M5 does not own either.
