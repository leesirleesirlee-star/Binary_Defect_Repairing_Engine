# Fixture design — stack-overflow-01

Owner: M3 (fixture + verifier).

## Scope

```text
architecture  i386
format        ELF32, ET_EXEC, no PIE, static
size          122 bytes
defect        read(0, buf[32], 64)
oracle        valid inputs exit 0; 40/64-byte inputs SIGSEGV
```

The fixture deliberately uses no libc. `_start` calls `vuln`; `vuln` subtracts
0x20 from ESP, reads up to 64 bytes into that 32-byte stack area, then executes
`leave; ret`. A 40-byte or 64-byte input overwrites the saved return address.

## Freeze

```text
contract.json   frozen
cases/          frozen
manifest.json   binary hash / metadata
```

M3 is the only role that edits `contract.json`, `cases/`, or `vuln.elf`.
M4/M5 may read them; they must not write them.

## Evidence

Static, on the authoring host:

```text
tests/fixture/test_fixture.py   10 passed
ELF32 / EM_386 / ET_EXEC        checked
no PT_INTERP                    checked
entry / sub esp,32 / read 64    checked by bytes
manifest/contract/case hashes   checked
```

Runtime:

```text
guest/run_cases.py -> observations.json   NOT RUN on authoring host
pipeline/verify/verdict.py -> verdict.json  requires observations
```

The host runs only the static tests. `guest/run_cases.py` refuses non-Linux
hosts with exit 2, so the fixture cannot be accidentally executed on Windows.

## G1 status

```text
fixture artifacts   COMPLETE
static checks       PASS
guest PoC run       PENDING (needs Linux guest)
G1 runtime signoff  NOT CLAIMED
```

This distinction is intentional: a static hash/code-shape check is not a
runtime PoC observation.
