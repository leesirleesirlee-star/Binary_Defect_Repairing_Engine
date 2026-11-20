# M5 dry-run repair tools

> **This is a dry-run version. It is not repair evidence, not a candidate and
> not a verdict.** G2 has not approved a repair plan; the real fixture must not
> be patched.

No candidate has been produced and no fixture has been executed or modified by
these tools.

## Scope

The tools implement the M5 side of issue #10:

- parse ELF64 headers, program headers, section headers and relocation targets;
- find zero-filled caves in an approved executable range;
- build a 5-byte redirect plus an x86-64 guard and write an edit manifest;
- apply the manifest only in memory for a structural self-check;
- run a one-shot preflight when M3 publishes the new fixture.

The tools do not read `pipeline/verify/`, `fixtures/**/cases/`, `pipeline/ai/`
or `fixtures/**/build/`. They do not write `candidate.elf` and do not write a
verdict.

### Fixture reservation vs product cave finder

ADR 0001's `0xDEF`-byte reserved tail is a **fixture-only gift** for MVP2. It is
not a product assumption:

- `cave_finder --start/--end` is the approved-range mode used by the fixture
  preflight;
- `cave_finder` without bounds calls `find_caves_in_segments()` and scans every
  file-backed R-X `PT_LOAD`; this is the product-facing interface;
- `patch_writer`/`validate_fixture` still take an explicit approved cave and
  never guess one;
- when no cave exists, the tool returns `no_candidate`/`unsupported`. Segment
  extension (ADR 0001 option A) is **not implemented** here because the current
  contract forbids it; a product fallback needs a future ADR and an
  agent-produced safety proof.

## Files

```text
pipeline/repair/elf64.py           ELF64 parser, vaddr/file map, dry-run edits
pipeline/repair/guard.py           hand-encoded x86-64 guard
pipeline/repair/cave_finder.py     zero-tail scan + overlap/reachability checks
pipeline/repair/patch_writer.py    manifest writer, no candidate
pipeline/repair/self_check.py      structural check, not a verdict
pipeline/repair/manifest_schema.py provisional shape + v1 mapping slots
pipeline/repair/validate_fixture.py one-shot preflight framework
```

Related notes: `guard-abi.md` (byte/ABI review), `m4-handoff-checklist.md`
(proposal cross-check), `repair-feasibility-note.md` (G2 pre-read),
`g2-review-QA.md`, `fixture-exception-handling.md`, `pr-submission-checklist.md`
and `manifest-verifier-mapping.md`.

## Risks and unverified assumptions

1. **The real fixture is not frozen yet.** The current M3 branch still has the
   old 0x211-byte R-X segment. ADR 0001 must be merged and M3 must rebuild with
   the reserved tail; only then can the real hash, addresses and reserved range
   be used. The tools reject the old fixture rather than guessing.
2. **The guard is only statically encoded here.** No test or host execution
   proves its runtime behavior. M3 must run the candidate in the disposable
   guest and apply the verifier.
3. **NUL-termination is assumed by the contract.** The guard scans up to 32
   source bytes for a NUL. If the guest passed a non-terminated buffer, the scan
   could read beyond the intended string; the contract is expected to rule that
   out.
4. **Partial writes are handled, but a failing stderr cannot satisfy the
   contract.** The guard loops on positive `write` results and exits 1 on error
   or zero. M3 must reject a candidate whose exact stderr bytes are missing.
5. **CET/shadow-stack enforcement is assumed absent.** The valid path is a tail
   jump to the original PLT stub; this relies on the environment assumptions in
   `ContractV1`.
6. **The manifest schema is provisional.** `EditManifestV1` has not been
   published by M1; the current `m5-dryrun-v0` / `EditManifestV1-draft` shape is
   deliberately local and must be replaced when the frozen schema exists.
   `manifest_schema.py` only reserves extension slots; it does not define a
   schema.
7. **The patch site is assumed to be the single eligible 5-byte call.** The
   writer checks the `E8` opcode, preimage, executable segment and rel32 range,
   but it does not disassemble the whole function.
8. **The current M3 fixture's `.fini`/segment facts are not revalidated here.**
   The cave finder requires a zero-filled, aligned, unreferenced range in the
   M3-provided manifest; it does not assume the old 0x401211 address.
9. **Determinism excludes evidence timestamps.** `created_at` is optional and
   excluded from `manifest_sha256`; the raw JSON is byte-identical only when the
   caller uses the same optional metadata. Tests cover the no-timestamp case.
10. **The preflight is not a gate decision.** A `dry_run_checks_passed` report
    means the fixture shape is usable by M5; it does not mean G1/G2 is approved
    or that a repair is correct.

## Commands

```bash
# 1a. Fixture preflight: approved range.
python -m pipeline.repair.cave_finder \
  --elf <original.elf> --start <reserved-start> --end <reserved-end> \
  --min-size 111 --patch-site <call-site>

# 1b. Product-facing scan: every file-backed R-X PT_LOAD.
python -m pipeline.repair.cave_finder \
  --elf <original.elf> --min-size 111 --patch-site <call-site>

# 2. Emit only a JSON manifest; no candidate is created.
python -m pipeline.repair.patch_writer \
  --elf <original.elf> --patch-site <call-site> --cave <cave> \
  --strcpy-plt <strcpy-plt> --cave-limit <reserved-end> \
  --fixture-id <fixture-id> --out var/manifest.json

# 3. Structural self-check; not a verdict.
python -m pipeline.repair.self_check \
  --elf <original.elf> --manifest var/manifest.json

# 4. One-shot preflight after the new fixture exists.
python -m pipeline.repair.validate_fixture \
  --elf <original.elf> --start <reserved-start> --end <reserved-end> \
  --patch-site <call-site> --strcpy-plt <strcpy-plt> \
  --manifest-out var/manifest.json --out var/preflight.json
```

## Status and error codes

| Tool | Exit 0 | Exit 1 | Exit 2 |
|---|---|---|---|
| `cave_finder` | at least one candidate | no candidate / unsupported range | malformed input |
| `patch_writer` | manifest written | — | rejected input, no manifest |
| `self_check` | `checks_passed` | `checks_failed` | malformed manifest/ELF |
| `validate_fixture` | `dry_run_checks_passed` | `no_candidate` / `unsupported` / `dry_run_checks_failed` | malformed input |

The status strings are deliberately not verdict vocabulary. `unsupported`,
`error`, `not_run` and `checks_failed` are never rendered as success. All four
CLIs support `--help` and `--version`; JSON output is emitted with sorted keys.

## Deterministic manifest

`patch_writer` writes JSON with sorted keys. `manifest_sha256` hashes the
canonical payload excluding `created_at`, the hash itself, and local
`original.path`/`contract.path` values. The same original ELF, patch site, cave
and guard therefore produce the same canonical hash across runs and checkouts.
`created_at` remains optional evidence metadata and is not part of that hash.

Golden snapshots live in `tests/repair/golden/manifest-cases.json`. They cover
one with-tail synthetic ELF (manifest hash + key fields) and one no-tail synthetic
ELF (deterministic `unsupported` refusal, no manifest). A failing golden test
must be investigated; the test never updates the snapshot automatically.

Malformed-ELF tests live in `tests/repair/test_malformed_elf.py`; every case must
fail closed (`ELFError`/`error`/`unsupported`) and must not write a manifest.

## Evidence for this change

```text
python -m pytest -q -m "not guest"    108 passed
python -m pytest -q tests/repair      79 passed
ruff check .                          passed (ruff 0.17.6)
```

The synthetic ELF used by the tests is built by `tests/repair/elf_builder.py`;
it is never the real fixture.

## Open questions for M1/M3/M4

- Which exact `EditManifestV1` shape and field names are frozen?
- Does the verifier accept the union of patch-site and reserved-range changes,
  and how does it independently prove every changed byte is authorized?
- What is the approved behavior for non-printable argv values and unavailable
  stderr?
- Who records G1/G2 approval, and on which exact fixture hash?
