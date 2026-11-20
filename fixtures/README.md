# Fixtures

Owned by M3 (`fixture` module). One fixture for MVP2:
`stack-overflow-01/`.

```text
stack-overflow-01/
├─ build/              C source + build script (BUILD-ONLY)
├─ vuln.elf            compiled original, committed
├─ manifest.json       hashes, flags, symbols, segment facts
├─ contract.json       frozen contract (M1 owns the text; M3 reviews)
└─ cases/              valid.json, invalid.json, poc.json
```

## Rules

- Only team-built or public teaching samples. No client binaries, no
  confidential derived content.
- `build/` is build-only. Analysis, AI, audit and repair code must not read it.
  A test enforces that no source path or source text reaches a prompt.
- Record provenance: source hash, compiler/ld versions, exact command, binary
  hash, environment.
- Keep symbols in v1 so the target function is identifiable. Stripping is a
  later variant, not a silent change.
- The fixture and corpus freeze at G1. A change is a new version and a new gate.
- The binary is committed; do not ignore `*.elf` globally.
