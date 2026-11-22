# `pipeline/verify` - deterministic checks and verdict writer

Owner: M3 (`verify` module). Gate: G3.

This package is the **only writer of `VerdictV1`**. It reads the frozen contract,
the frozen corpus, the guest observations, the `EditManifestV1` and the original
and candidate ELF bytes. It never executes an ELF, never reads the AI plan and
never imports `pipeline.ai`, `pipeline.audit` or `pipeline.repair`.

```text
pipeline/verify/elf64.py      read-only ELF64 parser (headers, sections, dynamic,
                              relocations); stdlib only
pipeline/verify/canonical.py  canonical JSON, hashes, status vocabulary
pipeline/verify/checks.py     V0-V5 check functions (no verdict label logic)
pipeline/verify/verdict.py    CLI, verdict assembly, success-rule enforcement
```

Only the existing `jsonschema` dependency is used (to validate inputs against the
frozen schemas and to refuse to write an invalid verdict). `capstone`/`pyelftools`
are not imported: the verifier decodes only the bytes the checks need.

## CLI

Candidate verification (G3 handoff H7 + H8):

```bash
python -m pipeline.verify.verdict \
  --contract fixtures/stack-overflow-01/contract.json \
  --cases fixtures/stack-overflow-01/cases/cases.json \
  --observations var/observations-candidate.json \
  --manifest var/edit-manifest.json \
  --original-elf fixtures/stack-overflow-01/vuln.elf \
  --candidate-elf var/candidate.elf \
  --out var/verdict.json
```

G1 original-binary check (kept for compatibility with
`fixtures/stack-overflow-01/original-check.json`):

```bash
python -m pipeline.verify.verdict --role original \
  --contract fixtures/stack-overflow-01/contract.json \
  --cases fixtures/stack-overflow-01/cases/cases.json \
  --observations fixtures/stack-overflow-01/observations-original.json \
  --out var/original-check.json
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | candidate is `verified_against_stated_criteria`, or the `--role original` check observed the original |
| 1 | a verdict was written but it is `rejected`, `unverified`, `unsupported` or `error` |
| 2 | an input file could not be read/decoded; no verdict was written |

`--now 2026-11-21T12:00:00Z` pins `produced_at` for reproducible test output.

## Checks

| Check | What it proves | Implementation |
|---|---|---|
| V0 identity | original hash = contract = manifest original; candidate hash = observation = manifest `preview.candidate_sha256_if_applied`; observed `argv_sha256` values match the frozen corpus; ELF header (except the entry field), program header table and section header table are byte-identical to the original; every changed byte is covered by a manifest edit range or by the ADR 0001 reserved tail `0x401211-0x402000`; the original tail is zero-filled | `check_identity` |
| V1 structure | candidate parses as ELF64 x86-64 `ET_EXEC`; entry unchanged; `PT_LOAD` count/flags unchanged; no W+X; `.dynamic`/`.dynsym`/`.dynstr` and `DT_NEEDED` unchanged; no relocation targets an executable segment (no text relocation); patch site is a declared 5-byte `E8` call whose rel32 target is the declared cave entry; the original call target matches the manifest's `strcpy@plt`; the cave is in the R-X `PT_LOAD`, inside the reserved tail, zero-filled in the original and holds exactly the declared trampoline bytes/hash; every edit has a matching preimage and postimage and maps vaddr to file offset; undo edits restore the original hash; applying the edits reproduces the candidate hash | `check_structure` |
| V2 valid behaviour | every `valid` case matches `expected_candidate` exactly: exit code, stdout bytes, stderr bytes, `signal: null`, `timed_out: false` | `check_valid` |
| V3 invalid response | every `invalid`/`poc` case exits 1, writes empty stdout, writes exactly `contract.stated_criteria.invalid_stderr` to stderr, has `signal: null` and no timeout; this includes the frozen 64-byte PoC case `invalid-64` | `check_invalid` |
| V4 boundary | a 31-byte valid case is accepted and a 32-byte invalid case is rejected by the observations (with `capacity - terminator == max_valid` consistency), **and** static evidence for either recognised guard layout (legacy or G2-selected plan) that the redirect target is inside the declared cave and that a length comparison against 31/32 precedes the tail jump to the original copy target, with no call to the copy target before the comparison | `check_boundary` |
| V5 reapply reproducibility (optional) | applying the manifest to the original in memory reproduces the candidate sha256 | `check_reapply` |

V4 static evidence is a bounded byte-pattern check over the declared cave code.
It recognises the two guard layouts G3 can hand it:

- the legacy `pipeline.repair.guard` layout (`cmp eax, 32` / `83 f8 20`);
- the G2-selected plan's guard (`cmp rdx, 31` / `48 83 fa 1f` after `inc rdx`,
  endbr64 + printable-ASCII scan, tail `e9 rel32` to `strcpy@plt`).

The matcher accepts the register compare-immediate forms
`83 /7 ib`, `48 83 /7 ib`, `81 /7 id`, `48 81 /7 id`, `3d id` and `48 3d id`
with an immediate of 31 or 32. It deliberately does not accept a memory compare
or `cmp al, 0x20`/`0x7e` (the printable checks) as a length bound. If the cave
code cannot be recognised (no boundary comparison, no tail jump to the copy
target), V4 is `not_run` with a reason, never `pass`. It is not a full
disassembly or a formal proof. The 90-byte selected-plan layout is locked by a
positive test (`test_selected_plan_guard_layout_passes_v4`) and a negative test
that removes the length compare.

## Verdict rules

`verdict` is a pure function of the criterion rows and the hash binding, computed
in one place (`pipeline.verify.verdict._decide`):

| Condition | `verdict` |
|---|---|
| every required check (V0-V4) `pass` and the identity hashes bind | `verified_against_stated_criteria` |
| any required check `fail` | `rejected` |
| any required check `not_run`, or the identity hashes do not bind | `unverified` |
| an input document is outside scope (`fixture_id`, schema/non-ELF64 original, invalid `EditManifestV1`) | `unsupported` |
| the verifier itself fails before a verdict exists | `error` |
| no criterion can be computed at all | `not_run` (never a success) |

`verified_against_stated_criteria` is scoped to the frozen `ContractV1` and
`CaseSetV1` of `stack-overflow-01`. It is not a proof of whole-program
correctness or security.

Defence in depth: `verify_candidate` refuses to return success unless the V0 hash
binding is true and every required row is `pass`, and `validate_verdict` refuses
to write a success whose required rows are not all `pass`. The frozen
`VerdictV1` schema is validated before the file is written.

## Missing is not passing

- A missing observation makes the affected V2/V3/V4 case `not_run`; the row
  aggregates to `not_run` and the verdict to `unverified`.
- A missing manifest preview hash makes V0 `not_run` (unverified).
- An unrecognised guard layout makes the V4 static part `not_run`.
- `criteria[].evidence_sha256` is `null` exactly for `not_run` rows; it is the
  sha256 of the canonical-JSON evidence payload for `pass`/`fail` rows.
- Reasons for every `not_run`/`fail` appear in `limitations`, and unmeasured
  cases plus `not_run` criterion ids appear in `coverage.unmeasured`.

## Determinism and reproducibility

- Evidence hashes are sha256 over canonical JSON (sorted keys, compact
  separators, UTF-8); the same inputs produce the same evidence hashes.
- `verdict_sha256` printed on stdout is sha256 over the canonical verdict with
  `produced_at` removed, so two runs on the same inputs agree even at different
  wall-clock times. Tests that need byte-identical files pass `--now`.
- `coverage.cases_run` counts corpus cases that have an observation; every other
  case is listed in `coverage.unmeasured`.

## Safety rules

- Parse bytes only: never execute, never write an ELF, never modify the original.
- Never read `docs/audit/fix-plan-v1.json`, `docs/audit/raw/**` or
  `fixtures/**/build/**`.
- The manifest is untrusted input: every value is re-derived from the ELF bytes
  or compared against the frozen fixture; the manifest's claimed hashes,
  invariants and reversibility are never trusted as evidence.
- `fixtures/stack-overflow-01` is the only in-scope fixture (ADR 0001 reserved
  tail). Another fixture needs a new verifier version and a gate.

## Tests

```bash
python -m pytest -q -m "not guest" tests/verify
```

`tests/verify/test_verifier.py` builds synthetic observations and an
`EditManifestV1`, applies the manifest to the frozen original **in memory** to
produce candidate bytes, and covers the pass path, every V0-V5 failure/not_run
path, the unsupported/error envelopes, the CLI, schema validation of the emitted
`VerdictV1` and the reproducible `verdict_sha256`. No test executes an ELF.
