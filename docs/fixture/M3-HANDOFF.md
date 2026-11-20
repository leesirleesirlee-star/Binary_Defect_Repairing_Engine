# M3 handoff — stack-overflow-01

Date: 2026-11-20  
Owner: M3 (fixture + verifier)

## Delivered

```text
fixtures/stack-overflow-01/
  vuln.elf
  manifest.json
  contract.json
  SHA256SUMS
  build/{build_elf.py,build.sh,vuln.c}
  cases/{poc.bin,valid/*,invalid/*}
guest/run_cases.py
pipeline/verify/verdict.py
tests/fixture/test_fixture.py
tests/fixture/test_verdict.py
docs/fixture/stack-overflow-01.md
```

## Pinned artifact

```text
file      fixtures/stack-overflow-01/vuln.elf
size      122 bytes
sha256    0f8633994016362d01809b18ab0aa3ed28ea01f1ccd96af52350c1bfaf68d9b0
class     ELF32, EM_386, ET_EXEC, no PIE, static
entry     0x08048054
```

## Oracle

```text
valid (0/6/32 bytes)       exit 0, no fatal signal
invalid (40 bytes)         SIGSEGV
PoC (64 bytes)             SIGSEGV
```

The PoC writes `0xdeadbeef` at the saved return-address slot (offset 36).

## Static evidence

```text
python -m pytest -q tests/fixture
10 passed

sha256sum -c fixtures/stack-overflow-01/SHA256SUMS
10/10 OK
```

The checks cover ELF32/EM_386/ET_EXEC, absence of PT_INTERP, code shape,
manifest/contract hashes, case lengths/hashes, and verifier decision logic.

## Runtime evidence

```text
guest/run_cases.py        NOT RUN on the Windows authoring host
pipeline/verify/verdict.py requires observations.json
```

The runner refuses non-Linux hosts with exit 2. Do not claim G1 runtime signoff
until a Linux guest produces `observations.json` and the verifier writes
`verified_against_stated_criteria`.

## Freeze

```text
contract.json   frozen
cases/          frozen
vuln.elf        frozen
```

Only M3 edits these files. M4/M5 may read them; they must not write them.
