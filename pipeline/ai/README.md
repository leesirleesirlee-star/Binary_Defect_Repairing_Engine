# `pipeline/ai` - provider transport and prompt builder

Owner: M4 (`ai` module). Gate: G2.

## Input

- `DisassemblyViewV1`.
- `ContractV1` (stated criteria, allowed edits, diagnostic hypothesis marked as a
  hypothesis).
- PoC input and its observed output.
- `FixPlanV1` JSON Schema.

## Output

- A parsed, schema-validated `FixPlanV1` or a typed failure
  (`provider_failed`, `invalid_output`, `timeout`, `unauthorized`).

## Rules

- The prompt never contains source, source paths, the valid/invalid corpus, the
  reference fix, the verifier code or a key.
- Model output is untrusted data. It cannot change the contract, the tools, the
  scope or the verdict.
- Record prompt hash, response hash, model id, token usage and timestamp.
- Three runs for the audit; no silent retry that hides a failure.
- The transport is adapted from the archive `binaryrepair_ai/client.py`; the old
  candidate schema and old prompts are not reused.
