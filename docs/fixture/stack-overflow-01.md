# Fixture design — stack-overflow-01 (x86-64, ADR 0001)

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
- `build/reserve_tail.py` extends the R-X `PT_LOAD` to `p_filesz = p_memsz =
  0x1000`, reserving the zero tail `0x401211-0x402000` (ADR 0001). No
  instructions are placed in the tail.

## Pinned artifact

```text
vuln.elf sha256  705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26
size             16016 bytes
R-X PT_LOAD      vaddr 0x401000, filesz=memsz=0x1000
reserved_range   0x401211-0x402000, 0xDEF bytes, zero_filled
handle frame     sub rsp,0x30; buf at rbp-0x20; saved RIP offset 40
```

## Evidence

```text
fixture-manifest.json / manifest.json   gcc-built, reproducible
observations-original.json              Linux guest, argv-based
verdict-original.json                   observed_original
SHA256SUMS                              regenerated after the tail step
tests/fixture                           ELF64/EM_X86_64, PLT, tail, hashes
```

The workflow `.github/workflows/build-fixture.yml` builds on `ubuntu-latest`,
runs the fixture tests and guest cases, and commits the artifact + manifest +
observations + SHA256SUMS.

## G1 status

```text
source/build recipe       COMPLETE
artifact                  COMPLETE (gcc + post-link tail reservation)
runtime original run      COMPLETE (observations-original.json)
G1 signoff                NOT CLAIMED by M3
```

G1 signoff still belongs to M1 after independent structural review.
