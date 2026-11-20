# Fixture design — stack-overflow-01 (x86-64)

Owner: M3 (fixture + verifier).

## Scope

```text
ELF64, EM_X86_64, ET_EXEC, non-PIE, dynamic libc
source is build-only: fixtures/stack-overflow-01/build/vuln.c
target function: handle (static, noinline, symbol kept)
buffer: 32 bytes
defect: strcpy(buf, input), unbounded
```

The source is quarantined by policy: `pipeline/analyze`, AI prompts and the
auditor must not read `fixtures/**/build/**`.

## Why this shape

- `handle` is a separate symbol, so G2 can slice its disassembly.
- `-O0 -fno-builtin` keeps `call strcpy@plt` as one 5-byte patch site.
- `-g0 -no-pie -fno-stack-protector` removes DWARF, PIE and canary side paths.
- `puts` gives a deterministic valid-path output.

## Evidence required

```text
build/vuln.elf + manifest.json + SHA256SUMS   gcc-built, reproducible
guest observations-original.json              Linux guest, argv-based
tests/fixture                                  ELF64/EM_X86_64, symbols, PLT
```

The workflow `.github/workflows/build-fixture.yml` builds on `ubuntu-latest`,
runs the fixture tests, and commits the artifact + manifest + SHA256SUMS. It is
the fallback when no local Linux toolchain exists.

## G1 status

```text
source/build recipe       COMPLETE
artifact                  PENDING gcc build
runtime original run      PENDING Linux guest
G1 signoff                NOT CLAIMED
```

A static header check is not a substitute for the guest observation.
