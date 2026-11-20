# Case sets

- `valid.json` - the correct inputs: 0, 1, 5, 31 bytes and a punctuation case.
- `invalid.json` - 32, 33, 64 and 128 bytes.
- `poc.json` - the 64-byte PoC and its observed original output.

The format is `CaseSetV1` in `schemas/`. Inputs are byte strings passed as
`argv[1]`, never shell strings. The set freezes at G1; a change needs a new
fixture version and a new gate.
