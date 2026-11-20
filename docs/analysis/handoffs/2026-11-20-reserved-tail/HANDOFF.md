# M4 to M5: Repair Proposal for the Reserved R-X Tail

**Date:** 2026-11-20
**Status:** Proposed; no patch approval or gate completion
**From:** M4 analysis draft, prepared for review
**To:** M5 repair owner
**Related:** [Issue #10](https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine/issues/10), [ADR 0001 / PR #14](https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine/pull/14), [verifier issue #11](https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine/issues/11)

## 1. Decision and current status

M4 accepts M1's proposed option B: M3 reserves the existing R-X segment tail **while building the new fixture**. A later candidate must keep the new original's program headers and section headers byte-identical. It must not extend a segment or add a segment when patching.

At the time this handoff was prepared, PR #14 was open and unmerged; the M3 branch still pointed to commit `20e102bbb28bc057784f0650429ae1d60572ed87`, whose binary SHA-256 was `10602531c92092cffbdc34688e12e4b97548cc2c03f4453506bdd4f1c9058d07`. This is the **old** fixture without the reserved tail. The new fixture and its hash were not yet available. Recheck all status and hashes before using this document.

This document is a proposed repair, not a candidate, an approved contract, a G2 decision, or proof of correctness. Before G2, issue #10 permits cave-finder and patch-writer **dry-run** work; do not apply a repair to the fixture or claim that a candidate is verified.

## 2. Input and evidence to obtain

1. Receive M3's newly built fixture, manifest, approved contract, new original SHA-256, and applicable G1 record. Keep the original read-only. The frozen corpus remains with M3; M5 must not read it.
2. Receive M4's fresh disassembly and tail survey for that exact hash. The old address `0x401194`, old call bytes `e8 c7 fe ff ff`, and old SHA-256 are observations for the old fixture only; remeasure them before preparing a plan.
3. Confirm the approved ADR/contract, repair location, permitted byte ranges, G2 decision, and designated reviewers. An open PR or this handoff is not evidence that those approvals occurred.
4. Confirm the reserved range from the **new** manifest and program headers. ADR 0001 proposes virtual addresses `[0x401211, 0x402000)`; those are provisional until verified on the new artifact. Map virtual addresses to file offsets using the new executable segment's actual header rather than assuming an offset.
5. Confirm the exact error-output semantics and the team's decision on short non-printable input and unavailable stderr. Do not infer an acceptance rule from this handoff or change the frozen corpus to fit a candidate.

## 3. Recommended repair logic

Assuming the new disassembly still exposes a single eligible 5-byte call to `strcpy@plt`, redirect that call to a guard in the approved reserved R-X range. The input is the same `strcpy` destination and source passed at the original call site. The guard must check the source before writing to the destination:

```text
for each source byte at index 0 through 31:
    if the byte is NUL:
        preserve the original destination and source arguments
        transfer to the original strcpy implementation
        return through the original call continuation

if no NUL appeared in those 32 bytes:
    write the exact approved error message to stderr
    exit with status 1, without reaching puts or writing to stdout
```

The terminator must fit inside the 32-byte destination. Thus a NUL at index 31 accepts a 31-byte input, while 32 non-NUL bytes are rejected before `strcpy` executes. Only this observed call path is addressed; this is not a general-purpose `strcpy` replacement.

On the normal path, preserve the x86-64 System V calling convention, original `rdi`/`rsi` arguments, return address, stack alignment where required, and callee-saved registers. A tail transfer to the existing `strcpy@plt` is one design to evaluate; its encoding, relocation, control-flow behavior, and return semantics must be checked on the actual new binary. Use of caller-saved registers is not by itself a proof of correctness.

On the rejected path, a Linux `write` syscall followed by `exit_group` is one possible design that avoids new dynamic imports. It still requires review of guest syscall policy, partial writes, interruption, fatal write errors, signal behavior, and termination semantics. A closed or failing stderr cannot be treated as successful exact output. Do not silently substitute truncation or return to the original `puts` path.

The stated error bytes are ASCII `ERROR: input exceeds destination capacity\n` (42 bytes including the newline). The current contract allows at most 256 bytes of added code and 64 bytes of added data; confirm these limits remain unchanged in the approved version. Do not include unused terminator bytes in emitted stderr.

## 4. Cave finder and patch writer: dry-run first

- Require the exact new original hash and approved contract version. Stop if they mismatch.
- Verify that the proposed reserved interval belongs to the approved executable `PT_LOAD`, is zero-filled and unreferenced according to the required checks, and does not overlap other sections, relocations, program headers, or load mappings **other than the intentionally containing R-X segment**. Check alignment and the next load-segment boundary. If any condition cannot be established, report `unsupported` or `inconclusive`; do not guess.
- Return a candidate location only if the actual guard, message, alignment, and any required branch reach all fit the approved bounds and size limits. The full proposed tail is not automatically approved for unlimited edits.
- Emit a dry-run edit manifest with original and proposed bytes, file offsets, virtual addresses, lengths, purpose, the original hash, and contract/plan identifiers. Check preimages, non-overlap, ranges, and branch displacement. Dry-run must not write the original or produce a claimed repaired candidate.
- Validate the manifest against independently approved bounds: the allowed call instruction and the approved reserved code/data interval. A manifest's own claims must not authorize unrelated changes. All changed candidate bytes should be accounted for by the validated manifest.
- Design rollback so the manifest restores changed bytes exactly; verify this on synthetic data before G2 and on a separately authorized candidate later. Preserve headers byte-for-byte and reject any unexpected change.

Issue #11 describes allowing changed bytes in the edit manifest or the reserved range. Please agree with M1/M3 how manifest authorization and tail accounting are enforced independently; the union alone does not prove that every change is contract-authorized.

## 5. Checks after authorization

**Not run by M4 for this handoff.** After the new fixture, approved location and contract, and G2 decision are available, M5/M3 should independently validate:

1. Identity: original and candidate hashes; original remains unchanged; manifest preimages and rollback match exactly.
2. Scope: program headers and section headers are byte-identical; all changes are independently permitted and fully accounted for; no extra segment, PLT/GOT import, text relocation, or W+X permission appears.
3. Loading and control flow: candidate loads in the disposable guest; the edited call reaches the reviewed guard; accepted inputs reach the original continuation with the required ABI and stack state.
4. Independent behavior checks: M3 alone runs the frozen corpus and checks exact output, exit status, and termination; M5 does not read the corpus. M5 can exercise synthetic boundary inputs derived from the approved contract, such as lengths 0, 31, and 32. Do not change frozen expectations to make the patch pass.
5. Error and boundary cases: independently test the contract's decisions on non-printable inputs and I/O failure when those assumptions are specified. Record timeouts, unknowns, crashes, missing evidence, and hash mismatches as non-passing.
6. Verifier: M3 uses the approved independent oracle and does not use the AI proposal as proof. G1/G2/G3 outcomes are recorded only by the responsible team members.

All binary parsing, candidate execution, and any compilation belong in the approved disposable guest. Preserve source separation and do not put credentials or build-only source material into the guest analysis output, model input, report, or edit manifest.

## 6. Questions for M5 and M1/M3

- Can the chosen guard and data fit the independently verified reserved interval within the code/data limits, while preserving calling conventions and exact error behavior?
- What concrete evidence proves the new tail is zero-filled, mapped R-X, unreferenced, and safe on the target guest?
- How will the verifier independently enforce allowed ranges and account for every changed byte?
- Who records approval of the new fixture, contract version, repair location, and G2 decision?

## 7. Packaged static evidence

The `evidence/` directory contains the static space survey and its supporting outputs for the old fixture hash. `cave-readelf.txt` has FILE-type symbol rows redacted to avoid including build-related names. Text line endings and trailing whitespace were normalized for repository storage; the evidence files are not byte-for-byte raw tool captures. The original binary, source, credentials and private keys are not included. These artifacts do not establish the new fixture or a passed gate.
