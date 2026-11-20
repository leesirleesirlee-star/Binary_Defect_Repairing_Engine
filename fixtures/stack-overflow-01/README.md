# `stack-overflow-01`

The MVP2 fixture: one C function with `char buf[32]` and an unbounded `strcpy`,
built as a non-PIE Linux x86-64 ELF with no stack protector.

- `build/` - source and build script. BUILD-ONLY.
- `vuln.elf` - compiled original (added by M3 at G1).
- `manifest.json` - hashes, flags, symbols and segment facts (G1).
- `contract.json` - frozen criteria (M1 owns the text; M3 reviews).
- `cases/` - valid, invalid and PoC cases (G1).
