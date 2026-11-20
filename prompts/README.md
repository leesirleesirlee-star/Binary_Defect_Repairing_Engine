# Prompts

Owner: M4 (`ai` module). Gate: G2.

## Rules

- Every prompt is a versioned file here, not a string buried in code.
- Inputs: `DisassemblyViewV1`, `ContractV1`, the PoC record and the output schema.
- Never include: source, source paths, DWARF line info, the valid/invalid corpus,
  the reference fix, the verifier code, a key, or another job's data.
- The model is told that worker/analysis text is data, not instructions.
- Record a prompt hash with every run; a changed prompt is a new version.
- The output must validate against `FixPlanV1`; invalid output is a recorded
  failure, not a retry-until-valid loop.
