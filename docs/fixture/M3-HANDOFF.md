# M3 handoff — stack-overflow-01 (x86-64)

Date: 2026-11-20  
Owner: M3 (fixture + verifier)

## Delivered

```text
fixtures/stack-overflow-01/
  build/vuln.c              exact MVP2 source (BUILD-ONLY)
  build/build.sh            exact gcc recipe
  build/record_manifest.py  post-build manifest recorder
  contract.json             frozen stated criteria
  cases/cases.json          argv-based corpus
  cases/poc.txt             64 x A PoC
  README.md
  cases/README.md
guest/run_cases.py           Linux guest observation runner
pipeline/verify/verdict.py   deterministic candidate/original verdict
tests/fixture/               ELF64/EM_X86_64 + verifier tests
docs/fixture/                design + this handoff
.github/workflows/build-fixture.yml
```

## Pending artifact

```text
vuln.elf, manifest.json, SHA256SUMS   PENDING gcc build
```

The build must run on Linux x86-64 with gcc/ld. The workflow builds twice,
requires equal sha256, records toolchain/ELF/symbol/frame facts, runs
`tests/fixture`, and commits the artifact on success.

## Required checks after build

```text
readelf -h vuln.elf              ELF64, EM_X86_64, EXEC
readelf -sW vuln.elf             handle, main, strcpy@plt, puts@plt
objdump -d vuln.elf              call strcpy@plt inside handle
readelf -d vuln.elf              NEEDED libc.so.6
readelf -sW vuln.elf             no stack_chk
manifest                         reproducible=true, actual saved_rip_offset
```

## Runtime

```bash
python3 guest/run_cases.py --fixture fixtures/stack-overflow-01 \
  --out var/observations-original.json
```

`observations-original.json` is required for G1. Do not claim G1 from the static
tests alone.

## Branch hygiene

M3 branch touches `fixtures/`, `guest/`, `pipeline/verify/` and `tests/fixture/`.
M1 should review with `module:integration`; split into fixture/guest/verifier
branches if the project requires one-module PRs.
