# stack-overflow-01 (x86-64, build-only source)

Frozen fixture for MVP2, built from `build/vuln.c` with gcc.

```text
target function   handle (static, noinline, symbol kept)
buffer            32 bytes
defect            unbounded strcpy into buf[32]
binary            ELF64, EM_X86_64, ET_EXEC, non-PIE, dynamic libc
valid             0..31 bytes: input + LF on stdout, exit 0
invalid           32+ bytes: candidate must exit 1, exact stderr, empty stdout
PoC               64 x 'A' passed as argv[1]; original SIGSEGV expected
```

## Provenance

`build/vuln.c` is **BUILD-ONLY**. Analysis, AI and audit code must not read
`build/`. The committed `vuln.elf` is produced by `build/build.sh` with the
exact flags in the spec, not by a byte generator.

```bash
gcc -O0 -g0 -fno-stack-protector -fno-pie -no-pie -fno-builtin \
    -m64 -Wall -Wextra -Wl,-z,noexecstack -Wl,--build-id=none \
    -o vuln.elf vuln.c
```

`build/record_manifest.py` runs after the build and records toolchain, command,
hashes, ELF headers/segments, symbols, `handle` frame, the ADR 0001 reserved
range, and reproducibility.

## Current build status

```text
vuln.elf sha256   705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26
size              16016 bytes
R-X PT_LOAD       vaddr 0x401000, filesz=memsz=0x1000
reserved_range    0x401211-0x402000, 0xDEF bytes, zero_filled
manifest          fixture-manifest.json (+ manifest.json alias)
runtime           observations-original.json, observed_original
```

The build is produced by `.github/workflows/build-fixture.yml` on
`ubuntu-latest` (or by a Linux guest), including the post-link
`build/reserve_tail.py` step. G1 signoff still belongs to M1.

## Run

```bash
python3 guest/run_cases.py --fixture fixtures/stack-overflow-01 \
  --out var/observations-original.json
python3 pipeline/verify/verdict.py \
  --contract fixtures/stack-overflow-01/contract.json \
  --cases fixtures/stack-overflow-01/cases/cases.json \
  --observations var/observations-original.json \
  --role original --out var/verdict-original.json
```
