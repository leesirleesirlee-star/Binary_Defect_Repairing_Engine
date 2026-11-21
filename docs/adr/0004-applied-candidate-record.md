# ADR 0004: the applied candidate gets its own record; `EditManifestV1` stays dry-run

- **Status:** accepted
- **Date:** 2026-11-21
- **Deciders:** M1 (contract/lead); M2, M3, M4, M5 informed
- **Related:** issue #45 (G3 candidate), PR #28 (`EditManifestV1` v1 CLI), issue #2 (schema publication plan), `schemas/README.md`

## Context

G3 must hand a real `candidate.elf` to M3, and M5 found a contradiction while
starting the apply step:

- `schemas/EditManifestV1.schema.json` is the **dry-run** manifest by design:
  `dry_run` is `const true` and `preview.candidate_written` is `const false`;
- `#45` asks for a written candidate **plus** a schema-valid `EditManifestV1`.

Both cannot be true at once. A manifest that sets `candidate_written: true` would
fail the schema, and one that keeps `candidate_written: false` after writing a
candidate would be factually false. M5 correctly refused to produce either.

`schemas/README.md` and issue #2 already list a G3 schema that was never
published: **`CandidateV1`** (producer M5, consumers M3 and M2).

## Decision

1. **`EditManifestV1` is unchanged.** It remains the truthful **dry-run** record
   of the bytes a candidate would change (`dry_run = true`,
   `preview.candidate_written = false`). It is not re-used for the applied state.
2. **Publish `CandidateV1`** as the applied-candidate record (as planned in
   `schemas/README.md`). G3 produces three artifacts:
   - the dry-run `EditManifestV1` (schema-valid, no candidate claim);
   - `candidate.elf` under `var/artifacts/<task>/` (never committed);
   - `CandidateV1` (schema-valid) stating `candidate_written: true`, the
     original/candidate hashes and sizes, the plan and manifest hashes, the edits
     actually applied, and the reversibility result.
3. **No false claim anywhere.** The manifest never claims a candidate; the record
   never claims a dry run. `CandidateV1` is the handoff artifact to M3 and the
   evidence record for the GUI/export.
4. **The verifier does not depend on `CandidateV1`.** It binds identity from the
   original ELF, the candidate ELF, the dry-run manifest and the guest
   `ObservationV1` (re-applying the manifest in memory and comparing bytes).
   `CandidateV1` is optional corroboration and must match when supplied.

## Consequences

- No change to a frozen schema; `CandidateV1` is an additive G3 schema and its
  example is covered by `tests/contract/`.
- G3 apply is unblocked: M5 writes the candidate, the dry-run manifest and
  `CandidateV1`; M3 runs the candidate in the guest and the verifier produces the
  verdict.
- The GUI/evidence layer can read `CandidateV1` from `var/artifacts/**` without
  inventing a success label; the verdict remains the verifier's alone.
