# `pipeline/analyze` - ELF facts and disassembly view

Owner: M4 (`analysis` module). Gate: G2.

## Input

- `vuln.elf` or `candidate.elf` path.
- `ContractV1` (target function, scope).

## Output

- `DisassemblyViewV1`: ELF header facts, segments, symbols, instructions with
  address/bytes/mnemonic/op_str, PLT stubs, sections.
- `FindingV1`: the suspected vulnerability site and the evidence.

## Rules

- Use `pyelftools` for headers/sections/symbols and `capstone` for decoding.
- Slice `handle`, `main` and the PLT stubs the target calls.
- The view contains **no source path, no DWARF line info and no source text**.
- Never read `fixtures/**/build/`.
- No model call, no execution, no network.

## Tests

- Decode known bytes and assert addresses/mnemonics.
- Serialize the view and assert no `.c` path, no `#include`, no source line.
- Feed a fake source path and assert the prompt builder rejects it.
