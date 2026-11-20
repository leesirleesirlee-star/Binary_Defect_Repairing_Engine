# ADR 0001: reserve an R-X tail in the fixture instead of extending the segment at patch time

- **Status:** accepted
- **Date:** 2026-11-20
- **Deciders:** M1 (lead); M3, M4, M5 informed
- **Supersedes:** none

## Context

M4's review request of 2026-11-20 ("Space for the Repair Guard") shows that the
current fixture has **no unused tail** in its executable segment:

- \`PT_LOAD\` R-X: file offset \`0x1000\`, vaddr \`0x401000\`, \`p_filesz = p_memsz = 0x211\`.
- Sections inside it: \`.init\` \`0x401000+0x1b\`, \`.plt\` \`0x401020+0x40\`,
  \`.plt.sec\` \`0x401060+0x30\`, \`.text\` \`0x401090+0x172\`, \`.fini\` \`0x401204+0xd\`.
- \`.fini\` ends at \`0x401211\`, exactly at the segment end. The only gaps are
  \`0x40101b-0x401020\` (5 bytes) and \`0x401202-0x401204\` (2 bytes); M4's
  "largest 15-byte padding" is 5 bytes by section arithmetic. Either way the
  result is the same: nothing near the 256 bytes the contract allows.
- File bytes \`0x1211-0x2000\` are all zero and are referenced by no section,
  relocation or program header. The next \`PT_LOAD\` starts at file offset
  \`0x2000\`, vaddr \`0x402000\`, R--.

The contract (\`fixtures/stack-overflow-01/contract.json\`) allows "at most 256
bytes in the existing R-X segment verified-unused tail". With no tail the
contract is unsatisfiable, which blocks the G1 freeze and the G2 audit. A
decision is needed now, before the fixture hash and the corpus are frozen.

## Options

1. **A - extend the R-X segment at patch time** (M4's recommended investigation).
   Leave the fixture untouched; let each candidate raise \`p_filesz\` into the
   zero gap. Cheapest for G1, but it moves an ELF structural edit into every
   candidate: the contract, \`FixPlanV1\`, the patch writer and the verifier all
   have to model and re-validate a program-header change, and the "no structural
   change" invariant that makes verification cheap is lost.
2. **B - reserve the tail at build time** (chosen). The build extends the R-X
   \`PT_LOAD\` to its page boundary (\`p_filesz = p_memsz = 0x1000\`) so the
   artifact ships a \`0xDEF\`-byte zero tail at \`0x401211-0x402000\` inside the
   existing segment. The contract text stays valid, the candidate stays
   byte-only, and the reservation is part of the recorded build recipe.
3. **C - add a second executable \`PT_LOAD\` at patch time.** Forbidden by the
   contract and the widest metadata surface; rejected.
4. **D - keep the contract and drop the cave approach.** Leaves MVP2 without a
   repair path; kept only as the fallback if B cannot be made reproducible.

The page-granularity fact that makes both A and B work is the same: the kernel
maps \`0x401000-0x402000\` as one R-X page, so bytes written inside that page
execute without any permission change. B settles that fact once, in the build,
instead of once per candidate.

## Decision

**Option B.** The fixture build extends the existing R-X \`PT_LOAD\` to
\`p_filesz = p_memsz = 0x1000\` (ending exactly at the next segment's
\`0x402000\`) and records the reserved range \`0x401211-0x402000\` in the
manifest. No instructions are planted in the tail; it stays zero.

Option A is not authorised for this fixture. It may be revisited only if B fails
reproducibility or structural validation, and then only through a new ADR with a
versioned contract.

## Consequences

- **Positive:** the frozen contract text stays valid; a candidate is still
  "one 5-byte call redirect plus code/data bytes"; the verifier can assert that
  program headers are byte-identical to the original; the AI plan needs no
  concept of ELF structure.
- **Negative:** the fixture hash changes, so G1 evidence must be regenerated
  (manifest, cases, \`SHA256SUMS\`, \`observations-original.json\`, analysis view).
  Nothing is frozen yet, so this is the cheap moment to do it.
- **Follow-up work:** see the acceptance conditions below.

## Acceptance conditions

M3 (fixture):

1. Extend the R-X \`PT_LOAD\` to \`p_filesz = p_memsz = 0x1000\` during the
   build, either with a linker-script fragment or a deterministic post-link
   step. \`p_offset\`, \`p_vaddr\` and \`p_flags\` must be unchanged.
2. Assert, in the build or in a test: the tail bytes \`0x1211-0x2000\` are all
   zero; no section, reloc or program header overlaps them; the next \`PT_LOAD\`
   still starts at \`0x402000\`.
3. Record in the manifest: \`reserved_range\` (vaddr start, end, size, all zero),
   the mechanism used, and the new \`sha256\`. Keep \`reproducible: true\`: two
   builds must yield the same hash.
4. Regenerate \`SHA256SUMS\`, \`cases/\`, \`contract.json.binary_sha256\` and
   \`observations-original.json\` in the guest, and stop claiming any G1 runtime
   sign-off until they match the new binary.

M4 (analysis): re-run the disassembly view on the new hash and confirm the
reserved range is visible as zero-filled, executable and unreferenced. No source
material enters the prompt.

M5 (repair): the cave finder must target the reserved range; the patch writer
must never edit program headers.

M3 (verify): new invariant for the verifier - the candidate's program headers and
section headers are byte-identical to the original, and every changed byte falls
inside the declared edit manifest or the reserved range.

M1: re-sign G1 with a dated record after the above, then close this ADR's
follow-up.

## Affected artifacts and owners

- Contract / schema: text unchanged; \`FixtureManifestV1\` gains an additive
  \`reserved_range\` field (M1).
- Fixture / corpus: rebuild and re-freeze (M3).
- Verdict vocabulary: unchanged.
- Module paths (\`modules.json\`): unchanged.
- CODEOWNERS: unchanged.

## Links

- Review request: M4, "Space for the Repair Guard", 2026-11-20 (not committed;
  attach to issue #4).
- Issues: #4 (fixture), #10 (cave finder), #11 (verifier).
- Gate: G1 re-freeze.
