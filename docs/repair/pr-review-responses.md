# PR review responses (M5 dry-run)

Scope: concise answers for PR #19 / G2 pre-review. All claims are limited to the
current synthetic-fixture toolchain; this is not a repair result.

## Q1. Why does this PR not generate a patch?

**Answer:** G2 has not approved a repair plan. M5 is authorized to build tools
and dry-run manifests only; applying a manifest to the real fixture or writing a
candidate would cross the G2 boundary. The PR deliberately emits no
`candidate.elf`; the only output is a JSON edit manifest whose `verdict` is
`null`.

**Evidence:** `pipeline/repair/patch_writer.py` writes only JSON;
`preview.candidate_written` is always `false`; tests assert no candidate file is
created.

## Q2. What is the tool boundary?

**Answer:** Static ELF parsing and byte-level edit planning only. The tools never
execute the fixture or a candidate, never write `verdict.json`, and do not import
`pipeline/verify`. Runtime behavior and correctness remain M3's independent
responsibility.

**Evidence:** `pipeline/repair/self_check.py` returns structural statuses, not
verdict vocabulary; `docs/repair/manifest-verifier-mapping.md` defines the
independent verifier boundary.

## Q3. What does the test coverage include?

**Answer:** Four dimensions:

- boundary/negative cases: malformed ELF, truncation, bad machine, huge counts,
  bad segment ranges, zero-length R-X, overlapping PT_LOAD;
- reversibility: inverse manifest edits restore the original SHA-256 at start,
  middle and end patch sites;
- determinism: canonical manifest hash is stable across paths and timestamps;
- golden snapshots for one with-tail sample and one deterministic no-tail
  refusal.

All data is synthetic; the real fixture is never touched.

**Evidence:** `tests/repair/test_malformed_elf.py`,
`tests/repair/test_negatives.py`, `tests/repair/test_golden_manifest.py`,
`tests/repair/golden/manifest-cases.json`.

## Q4. Is the change within M5 ownership?

**Answer:** Yes. Only `pipeline/repair/`, `tests/repair/` and `docs/repair/` are
changed. The module check passes with `module:repair`; no fixture, schema,
verifier, app or contract file is modified.

**Evidence:** `python scripts/check_modules.py --base origin/main --labels module:repair`
returns OK for every changed file.

## Q5. What remains unverified?

- PR #14 / ADR 0001 is not in `main`; the new fixture with the reserved tail is
  not published.
- Patch-site, reserved-range and `strcpy@plt` addresses are synthetic examples.
- Runtime ABI/exit/stderr behavior is not executed on the host.
- `EditManifestV1` is not frozen; the manifest uses provisional extension slots.

These are explicitly reported; none is presented as passed.
