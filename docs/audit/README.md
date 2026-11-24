# Audit reports

Owner: M4 (`audit` module). Gate: G2.

Contents: the three-run report, raw responses with the key removed, prompt and
response hashes, the rubric table and the signed decision.

Rules: every run stays in the table, including invalid JSON; the contract, corpus
and rubric are fixed before the runs; no self-scoring.

## Live runs vs the signed G2 record

`docs/audit/raw/` and `2026-11-21-audit-01.md` are the **signed G2 evidence** — the
frozen fixture/contract/corpus at their recorded hashes, the fixed prompt and the
reviewer scores. Do not edit them.

A console run may execute `python -m pipeline.audit` again from the API host
(`--summary-out PATH` writes the machine-readable `{model, prompt_sha256,
contract_sha256, runs:[...]}`). That is a **live** run, not new G2 evidence: the
G2 decision stays bound to the signed record, and a live result is labelled by its
own provenance (model, prompt hash, contract hash, timestamp) rather than
inheriting the G2 verdict. `canonical_plan_hash` gives a format-independent plan
hash so a live plan and the frozen plan compare by content, not JSON spacing.

