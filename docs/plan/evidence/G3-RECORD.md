# G3 gate record — applied candidate and deterministic verdict

- **Gate:** G3 (Repair + verify)
- **Date:** 2026-11-22 (Asia/Shanghai)
- **Signed by:** M1 `@leesirleesirlee-star`
- **Commit under verification:** `bb96a6c` (`main`: apply CLI #50, verifier V0–V5 #47, runner #52, console #51, GUI decision persistence #54)
- **Tag:** `candidate-v1` (annotated tag on this record's squash merge commit)
- **Evidence bundle:** `docs/plan/evidence/g3/` (committed in this PR, byte-exact)

## 1. Inputs frozen at G1 (unchanged)

| Artifact | SHA-256 |
|---|---|
| `fixtures/stack-overflow-01/vuln.elf` | `705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26` |
| `fixtures/stack-overflow-01/contract.json` | `856b6ad2dabf69b705836f3a7c6466b534034cb1a4770a43f3fb596a11ce578c` |
| `fixtures/stack-overflow-01/cases/cases.json` | `fae5efd054358d16610987f5645eadc582ce53ac12debeb356941d6617ceec3d` |

M1 re-checked all three hashes against the G1 record and `SHA256SUMS`; the fixture was not
modified by any G3 step. M3 (corpus owner) confirmed the frozen corpus and contract are the
G1 bytes; no corpus change is claimed or hidden.

## 2. Candidate

Produced deterministically from the G2-selected plan (no execution):

```bash
python -m pipeline.repair.apply_fixplan \
  --elf fixtures/stack-overflow-01/vuln.elf \
  --plan docs/audit/fix-plan-v1.json \
  --out-dir var/artifacts/g3-verify
```

- `candidate.elf` SHA-256: `c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28`
  (pinned by `CANDIDATE_SHA` in `tests/repair/test_apply_fixplan.py`; M1 re-generated it from
  `main` and got the same hash).
- Dry-run `EditManifestV1`: `dry_run=true`, `preview.candidate_written=false`,
  `reversibility.matches_original=true`; the manifest restores the original bytes exactly.
  (The manifest file hash differs per run because `created_at` is part of the dry-run record;
  the candidate hash is stable and is the identity used here.)
- `CandidateV1`: `candidate_written=true`, `original/candidate/plan/manifest` bound by file
  hashes (ADR 0004).
- The candidate binary is **not committed** (`var/` is gitignored by design); identity is the
  hash above, reproducible from the frozen fixture plus the committed plan and CLI.

## 3. Guest run (M3)

- Runtime: **Ubuntu 24.04 under WSL2, fresh boot** (`wsl --terminate Ubuntu`),
  kernel `6.18.40.1-microsoft-standard-WSL2`, glibc 2.43.
- Staging: a copy of `fixtures/stack-overflow-01/` whose `vuln.elf` is the candidate
  (contract and `cases/cases.json` unchanged); the frozen fixture itself was not modified.
- Command: `python3 guest/run_cases.py --fixture fixture-candidate --out observations-candidate-wsl2.json`
  (default 2 s timeout per case; no ELF execution on the Windows host).
- Observation file: `docs/plan/evidence/g3/observations-candidate-wsl2.json`, SHA-256
  `BB02D3D63C695FF198E2C447474015BC7281E4C62C5C205BF129543E471E7C23`, 9/9 cases recorded.
- Observed behaviour: valid cases exit 0 with stdout = argv + LF; invalid 32/33/64/128 exit 1,
  empty stdout, the exact 42-byte `invalid_stderr`, `signal: null`, no timeout.

## 4. Verdict (deterministic verifier is the only writer)

```bash
python -m pipeline.verify.verdict \
  --contract fixtures/stack-overflow-01/contract.json \
  --cases fixtures/stack-overflow-01/cases/cases.json \
  --observations var/artifacts/g3-verify/observations-candidate-wsl2.json \
  --manifest var/artifacts/g3-verify/edit-manifest.json \
  --original-elf fixtures/stack-overflow-01/vuln.elf \
  --candidate-elf var/artifacts/g3-verify/candidate.elf \
  --role candidate --now 2026-11-22T11:06:48Z \
  --out var/artifacts/g3-verify/verdict-wsl2.json
```

- Verdict: **`verified_against_stated_criteria`**
- Checks: V0 identity, V1 structure, V2 valid behaviour, V3 invalid response, V4 boundary all
  `required: true, status: "pass"`; V5 re-apply (optional) also `pass`. Coverage 9/9,
  `unmeasured: []`.
- Verdict file: `docs/plan/evidence/g3/verdict.json`, SHA-256
  `07C7529CD792E70A505A65DCA5621B9956DE2578554AD7064D00E690C1527B78` (byte-exact copy of
  M3's output; serialized `indent=2, sort_keys=True` plus newline, CRLF on the producer host).
- Canonical verdict hash (`produced_at` excluded): `51f29be55aea38070029429b1102eb7a0ee1557dbf99b15cdce64440e5bec45c`.

**M1 independent reproduction.** Using the committed observation file, a locally re-generated
candidate (`c010c006…`) and dry-run manifest from `main`, with the same `--now`, the merged
verifier produced an **identical verdict object and identical canonical verdict hash**
(`51f29be5…`). This verifies that the verdict follows from the frozen inputs and the merged
verifier, not from a hand-edited file.

**Second run (corroboration).** M3's earlier run in WSL1 (kernel `4.4.0-19041-Microsoft`) gave
observation SHA-256 `4441D9CE722696A4255DD380E56177934D7C5D694F92D906F3C31EE62BE58E78`
with the same verdict word, the same canonical verdict hash, and the same 9/9 coverage.

## 5. Isolation limitation (recorded, not hidden)

The runtime was a **fresh-boot lightweight WSL2 VM**, not a dedicated disposable
Multipass/Hyper-V guest, and no enforced no-network policy was applied. The guest module's
strict isolation claim ("disposable Linux VM or container snapshot, no network, no
credentials") is therefore **only partially satisfied**:

- satisfied: a separate Linux kernel/VM, fresh boot before the run, no provider key or
  credentials passed in, no host execution of the ELF;
- open: dedicated disposable image and enforced network isolation. A strict-isolation replay
  is recorded here as an **open item**, not as passed.

This does not change the verdict's scope (the verifier compares observations to the frozen
contract/corpus), but it is part of the honest evidence chain.

## 6. What G3 claims and does not claim

- Claims: for the frozen fixture `stack-overflow-01`, the candidate `c010c006…` produced from
  the approved G2 plan shows the contract's stated behaviour on the frozen corpus
  (valid 0..31 unchanged; invalid 32+ → exact stderr + exit 1, no crash), and the deterministic
  verifier returned `verified_against_stated_criteria` on those observations, reproduced
  independently.
- Does not claim: whole-program correctness, absence of other vulnerabilities, security of the
  binary, or similarity to any other build; the verdict is scoped to the written contract and
  corpus. No G4 demo (console end-to-end run) is recorded by this gate yet.

## 7. Signature

Gate G3 is signed off on the evidence above.

- M1 `@leesirleesirlee-star`, 2026-11-22
