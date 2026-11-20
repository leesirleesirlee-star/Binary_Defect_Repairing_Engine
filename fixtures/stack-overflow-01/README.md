# stack-overflow-01 (M3 fixture)

Frozen 32-bit Linux fixture for the new MVP.

```text
defect        CWE-121 stack buffer overflow
buffer        32 bytes
read          64 bytes into buf[32]
binary        ELF32, EM_386, ET_EXEC, no PIE, static, 122 bytes
PoC           64 bytes; overwrites saved return address with 0xdeadbeef
valid inputs  0, 6, 32 bytes: exit 0, no fatal signal
invalid       40 bytes: SIGSEGV
```

## Files

```text
vuln.elf                 committed artifact (canonical)
build/build_elf.py       reproducible freestanding builder (Python only)
build/build.sh           wrapper
build/vuln.c             reference C shape; not the canonical bytes
manifest.json            hashes, ELF metadata, oracle
contract.json            frozen expected behavior (M3-owned)
cases/poc.bin            64-byte PoC
cases/valid/*.bin        valid corpus
cases/invalid/*.bin      invalid corpus
```

`contract.json` and `cases/` are frozen by M3. AI analysis may read the
binary and manifest but must not write these files.

## Build

```bash
cd fixtures/stack-overflow-01/build
./build_elf.py
```

The builder needs only Python 3. No cross-compiler is required. It writes
`../vuln.elf`; the manifest hash must then be updated only by M3.

## Run in the guest

Never run the ELF on the Windows host.

```bash
python3 guest/run_cases.py \
  --fixture fixtures/stack-overflow-01 \
  --out var/observations.json
python3 pipeline/verify/verdict.py \
  --contract fixtures/stack-overflow-01/contract.json \
  --observations var/observations.json \
  --out var/verdict.json
```

Expected verdict: `verified_against_stated_criteria`.

## Runtime status

The artifact is statically checked (ELF32/EM_386/ET_EXEC, code shape, hashes,
case lengths) but **not executed on the authoring Windows host**. Runtime
execution and the SIGSEGV observation must be produced in the Linux guest; do
not mark the fixture runtime-verified until `run_cases.py` has an observation
file.
