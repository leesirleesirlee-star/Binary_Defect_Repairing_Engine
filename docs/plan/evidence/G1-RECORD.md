# G1 gate record — fixture freeze

- **Gate:** G1 (Fixture + PoC)
- **Date:** 2026-11-20 (Asia/Shanghai)
- **Signed by:** M1 `@leesirleesirlee-star`
- **Commit:** `2cb4f1d` (squash merge of #27)
- **Tag:** `fixture-v1`

## 1. What is frozen

| Artifact | Path | SHA-256 |
|---|---|---|
| binary | `fixtures/stack-overflow-01/vuln.elf` | `705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26` |
| contract | `fixtures/stack-overflow-01/contract.json` | `856b6ad2dabf69b705836f3a7c6466b534034cb1a4770a43f3fb596a11ce578c` |
| manifest | `fixtures/stack-overflow-01/fixture-manifest.json` | `ea4bfe6d1b96bb6a01f8e52c5c0343dee1d0a9865905cc062aa6aade2b9ae484` |
| corpus | `fixtures/stack-overflow-01/cases/cases.json` | `fae5efd054358d16610987f5645eadc582ce53ac12debeb356941d6617ceec3d` |
| observations | `fixtures/stack-overflow-01/observations-original.json` | `72638ca93eab90c5c471ac498969ce4d211eab91fcfa8a799dd9b7d37b4a767e` |

The corpus holds 9 cases (5 valid, 4 invalid, including the 64-byte PoC).

## 2. Build provenance

```text
gcc -O0 -g0 -fno-stack-protector -fno-pie -no-pie -fno-builtin \
    -m64 -Wall -Wextra -Wl,-z,noexecstack -Wl,--build-id=none \
    -o vuln.elf vuln.c
gcc 15.2.0 (Ubuntu), GNU ld 2.46, built on ubuntu-latest in CI
```

`fixture-manifest.json` records the toolchain, the command, the source hash, and
`reproducible: true` with an identical `second_sha256`.

## 3. ADR 0001 — reserved R-X tail

Measured by M1 directly on the merged bytes, not read from the manifest:

```text
class / machine / type   ELF64 / EM_X86_64 / ET_EXEC
entry                    0x401090
R-X PT_LOAD              offset 0x1000, vaddr 0x401000, filesz = memsz = 0x1000
reserved range           0x401211 - 0x402000 (3567 bytes), all zero
next segment             0x402000
```

The tail is zero-filled and unreferenced; the contract wording is unchanged and
remains satisfiable, as ADR 0001 intended.

## 4. Contract and corpus

- `contract.json` validates against `ContractV1`, with `criteria_source: "human_frozen"`
  and `binary_sha256` equal to the binary above.
- `cases.json` validates against `CaseSetV1`; valid inputs are 0..31 bytes,
  invalid inputs are 32..128 bytes, and the PoC is 64 `A` bytes.
- `observations-original.json` validates against `ObservationV1` and binds to
  `705ab929...`: the 64-byte PoC is recorded as `SIGSEGV`, all valid cases exit 0.

## 5. Verification performed

Run by M1 at `2cb4f1d` on the merged bytes:

1. Independent ELF parse (program headers, segment sizes, tail bytes) — results above.
2. `jsonschema` validation of contract, manifest, corpus and observations against
   the frozen schemas — all pass.
3. Hash comparison between the contract, the manifest, the observations and the
   binary — all bind to `705ab929...`.

The runtime observations were produced in the guest by M3 (`guest/run_cases.py`);
no fixture was executed on the host.

## 6. What G1 does not claim

- No AI audit has run; G2 has not started.
- No repair implementation has been merged; G2 is a hard stop before that.
- This record freezes one fixture and one contract; it says nothing about other
  binaries, defect classes or whole-program correctness.

## 7. Signature

Gate G1 is signed off on the evidence above.

- M1 `@leesirleesirlee-star`, 2026-11-20
