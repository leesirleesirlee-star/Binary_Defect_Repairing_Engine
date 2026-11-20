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
hashes, ELF headers/segments, symbols, `handle` frame, and reproducibility.

## Current build status

```text
vuln.elf, manifest.json, SHA256SUMS   PENDING the gcc build
build source + workflow              committed
```

The build is produced by `.github/workflows/build-fixture.yml` on
`ubuntu-latest` (or by a Linux guest). Do not claim G1 until
`vuln.elf`, `manifest.json` and `observations-original.json` exist.

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
