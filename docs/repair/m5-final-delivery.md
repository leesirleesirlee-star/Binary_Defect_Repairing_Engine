# M5 final delivery — repair implementation archive

- **Status:** M5 implementation closed; G1/G2/G3 signed, G4 remains the only open gate
- **Main baseline at PR time:** `058d670` (G4 export/ADR PRs #57/#58 merged)
- **Scope:** `pipeline/repair/`, `tests/repair/`, `docs/repair/`
- **Archive branch:** `archive/repair/11-hardening-old` (`2568d8d`, local-only; not pushed)
- **M5 does not write verdicts.** The official G3 verdict belongs to M3 and is recorded in
  [`docs/plan/evidence/G3-RECORD.md`](../plan/evidence/G3-RECORD.md).

## 1. Tool inventory

All paths are relative to the repository root.

| Tool | Main status | Purpose |
|---|---|---|
| `pipeline/repair/elf64.py` | merged | read-only ELF64 parser, segment/vaddr/offset mapping, bounded edit preview |
| `pipeline/repair/cave_finder.py` | merged | reserved-tail cave discovery and preflight |
| `pipeline/repair/patch_writer.py` | merged | dry-run patch builder and legacy/v1 manifest CLI |
| `pipeline/repair/manifest_schema.py` | merged | provisional-to-`EditManifestV1` mapping and shape validation |
| `pipeline/repair/canonical.py` | merged | path-independent canonical manifest hash |
| `pipeline/repair/self_check.py` | merged | headers/entry/segments/dynamic/edit coverage/reversibility |
| `pipeline/repair/validate_fixture.py` | merged | frozen-fixture structural validation |
| `pipeline/repair/fixplan_reader.py` | merged | read-only official `FixPlanV1` parser and fixture pre-check |
| `pipeline/repair/apply_fixplan.py` | merged | G3 apply CLI: candidate + dry-run manifest + `CandidateV1` |
| `pipeline/repair/implementability_scorer.py` | **local branch only** `feat/repair/p0-final-local` @ `3bc4eb8` | G2 15-point implementability scorer; not required for G3/G4 and not merged |

The implementability scorer was used for the G2 review and its result is frozen in the G2
record; the G3/G4 path does not depend on the scorer being on main.

## 2. Stage outputs

### P0 — dry-run toolchain

- Official structural preflight on the frozen fixture: `dry_run_checks_passed`.
- Report: [`docs/repair/preflight-report-official.md`](preflight-report-official.md).
- The preflight wrote no candidate and produced no verdict.

### G2 — implementability review

- M5 score for the selected plan: **15/15**, no critical error, `reviewer_scores.m5 = 100`.
- Selected plan: `docs/audit/fix-plan-v1.json`; stored file SHA-256
  `be2401a6210e3d7a7ef9f42fc26e466bf5400a2955dda05a8c95f81c525c9056`.
- Audit record's `plan_sha256` is `c16d97ba...`, identifying the model response
  (`plan-c16d97ba9bc0`); it is **not** the stored plan file hash. The hash chain below
  uses the stored-file hash `be2401a6...`.
- G2 decision and record: [`docs/plan/evidence/G2-RECORD.md`](../plan/evidence/G2-RECORD.md).
- M5 reviewed only Implementability plus the critical-error gate; M1 owns the other rubric
  dimensions and the G2 decision.

### G3 — applied candidate

Generated from the approved plan by `pipeline.repair.apply_fixplan`:

```bash
python -m pipeline.repair.apply_fixplan \
  --elf fixtures/stack-overflow-01/vuln.elf \
  --plan docs/audit/fix-plan-v1.json \
  --out-dir var/artifacts/g3-replay
```

Observed local replay:

| Artifact | Value |
|---|---|
| fixture SHA-256 | `705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26` |
| plan SHA-256 | `be2401a6210e3d7a7ef9f42fc26e466bf5400a2955dda05a8c95f81c525c9056` |
| manifest canonical SHA-256 | `eb98f1262eee428fee70f600ce7fc6db18189299ff8d9c4ef1fc5ca1bfc9d5f1` |
| candidate SHA-256 | `c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28` |
| restored fixture SHA-256 | `705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26` |
| self-check | `checks_passed` |
| reversibility | `matches_original: true` |

The candidate hash matches the signed G3 record. The manifest file hash changes with
`created_at`; the path-independent canonical manifest hash is stable and is the value used
for the chain above. `EditManifestV1` remains `dry_run=true` /
`preview.candidate_written=false`; `CandidateV1` is the truthful applied record with
`candidate_written=true` (ADR 0004).

The official G3 runtime evidence and verdict are in
[`docs/plan/evidence/g3/`](../plan/evidence/g3/); the official verdict word is
`verified_against_stated_criteria` with canonical verdict hash `51f29be5...`. M5 did not
produce or alter that verdict.

## 3. Evidence chain

```text
fixture 705ab929...9c26
  -> contract 856b6ad2...e578c
  -> corpus fae5efd0...ec3d
  -> approved FixPlanV1 be2401a6...c9056
  -> canonical EditManifestV1 eb98f126...d5f1
  -> candidate c010c006...b28
  -> inverse apply -> fixture 705ab929...9c26
```

Each step has a checked-in schema or test where applicable:

- `schemas/FixPlanV1.schema.json`, `tests/repair/test_fixplan_reader.py`
- `schemas/EditManifestV1.schema.json`, `tests/repair/test_manifest_v1.py`
- `schemas/CandidateV1.schema.json`, `tests/repair/test_apply_fixplan.py`
- `tests/repair/test_self_check.py`, `tests/repair/test_boundaries.py`

## 4. Reproducibility and tests

Main baseline checks:

```text
pytest -q tests/repair                              104 tests, passed
pytest -q -m "not guest" \
  --deselect tests/app/test_loader.py::test_symlink_escape_is_rejected
                                                    exit 0, 343 collected, 1 deselected
                                                    (Windows symlink privilege; Linux CI runs it)
ruff check pipeline/repair tests/repair              All checks passed
check_modules.py --base origin/main --labels module:repair   OK
```

The one known Windows-only failure is `tests/app/test_loader.py::test_symlink_escape_is_rejected`
(`WinError 1314`, symlink privilege); it is outside M5 scope and is covered by Linux CI. The
GitHub `test` job on main is green.

## 5. Compliance statement

- No candidate was generated before G2 approval.
- The frozen fixture was never modified; `fixture_unchanged=true` is checked by the apply CLI.
- No edits were made outside `pipeline/repair/`, `tests/repair/`, `docs/repair/` by M5.
- M5 did not modify audit, ai, verify, app, infra, contract, schemas or fixtures.
- M5 did not write or infer a verdict; G3 correctness is the signed M3/verifier result.
- All repair bytes are bound to the G2-approved `FixPlanV1`; no new unapproved repair logic
  was introduced.
- The local archive branch preserves the old hardening work; it was not pushed as product code.

## 6. Known limitations and dependencies

- Correctness is runtime evidence from M3; M5's self-check is structural only.
- Scope is the frozen `stack-overflow-01` fixture, contract and corpus; this is not a general
  binary-repair claim.
- The G3 guest was a fresh-boot WSL2 VM, not a fully disposable/no-network guest; this open
  limitation is recorded in the G3 record.
- The implementability scorer is local-only and not required by the merged apply/verifier path.
- G4 console/export is not signed yet; M5 provides reference artifacts but does not approve or
  modify G4 PRs (#56/#57/#58).

## 7. G4 handoff reference

The merged runner export bundle (#57) lists `candidate.elf`, `edit-manifest.json`, `candidate-v1.json`,
`verdict.json`, `observations-candidate.json`, `disassembly.json` and `finding.json`. M5 owns
the first three and their names/meanings match the export list:

| File | Meaning | Identity |
|---|---|---|
| `candidate.elf` | applied candidate, never committed | SHA-256 `c010c006...` |
| `edit-manifest.json` | dry-run manifest; `candidate_written=false` | canonical `manifest_sha256` `eb98f126...` |
| `candidate-v1.json` | applied record; `candidate_written=true` | candidate/plan/manifest hashes bound |

No runner/frontend code was changed by M5 for G4. If the console shows a repair field
differently, this table is the M5 reference; the fix belongs to the owning module.
