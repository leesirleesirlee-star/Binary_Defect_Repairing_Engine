# M5 repair feasibility note (G2 pre-read)

Status: **dry-run proposal, not an approval and not a verdict**. For M4's audit
and the G2 decision; it does not replace the formal review record.

## 1. Byte budget

| Item | Bytes | Limit | Headroom |
|---|---:|---:|---:|
| Guard code (scan + write/exit + tail jump) | 69 | 256 | 187 |
| Frozen stderr message | 42 | 64 | 22 |
| **Total written into the cave** | **111** | — | — |

The 42-byte message is exactly `ERROR: input exceeds destination capacity\n`
(0x2a bytes, including LF). The guard starts on a 16-byte boundary; the example
16-byte-aligned start is `0x401220`, still inside ADR 0001's reserved range.

## 2. Structural invariants promised

The generated manifest and structural self-check enforce:

- no new `PT_LOAD`, no deleted `PT_LOAD`;
- program headers and section headers byte-identical to the original;
- entry point unchanged;
- segment permissions unchanged, no W+X load segment;
- no new dynamic import; `.dynamic` bytes unchanged when present;
- every changed byte is covered by a manifest edit;
- inverse edits restore the original file hash exactly.

M5 never edits headers; a future product that needs segment extension requires a
new ADR and must be handled as a separate, explicitly-authorized mode.

## 3. Verifiability

- **Reversible:** each edit records file offset, vaddr, original bytes, patch
  bytes and purpose; applying inverse edits restores the original SHA-256.
- **Accountable:** `self_check` computes the byte diff between original and
  in-memory preview and rejects any changed byte outside the manifest edits.
- **Deterministic:** `manifest_sha256` excludes the optional `created_at`
  metadata; the same input and options produce the same canonical hash and JSON
  bytes.
- **Independent:** M5 does not import `pipeline/verify`, does not read the
  corpus, does not execute the ELF and writes `verdict: null`.

## 4. Known limits and dependencies

1. **Reserved tail must exist.** ADR 0001 must be merged and M3 must rebuild the
   fixture with a file-backed `p_filesz=p_memsz=0x1000` R-X segment. Without it
   the tools return `unsupported`, not a guessed patch.
2. **New hash/addresses must be re-measured.** The example `0x401194`,
   `0x401211-0x402000`, `0x401060` are not frozen facts.
3. **Contract semantics are M1-owned.** M5 does not change valid length, error
   bytes, exit code or stderr behavior.
4. **Runtime correctness is M3-owned.** No host execution; no candidate; no
   verdict. The guest must produce observations and the verifier must decide.
5. **Product code-space problem is not solved by the fixture gift.** The fixture
   reservation only exists for MVP2. The product cave finder must scan all
   file-backed executable segments; if no cave exists, it must return
   `no_candidate` and the segment-extension fallback requires a future ADR plus
   agent-produced safety evidence. It must not silently extend a segment.

## 5. G2 questions

- Is 69+42 bytes acceptable within the approved plan's edit budget?
- Does the guard's ABI/tail-jump behavior match the approved call-site shape?
- Does the verifier independently enforce the same byte/range invariants?
- Is the product fallback (segment extension) explicitly out of MVP2 scope?
