# G2 gate record — AI audit and plan decision

- **Gate:** G2 (AI audit)
- **Date:** 2026-11-21 (Asia/Shanghai)
- **Signed by:** M1 `@leesirleesirlee-star`
- **Commit:** `57480bf` (squash merge of #41; the audit evidence)
- **Tag:** `audit-v1` (annotated tag on `57480bf`, the audit evidence commit)
- **Report:** `docs/audit/2026-11-21-audit-01.md` (finalized in #44)
- **Machine report:** `docs/audit/2026-11-21-audit-01.json` (validated against
  `schemas/AuditReportV1.schema.json`)

## 1. Inputs frozen at G1 (unchanged)

| Artifact | Path | SHA-256 |
|---|---|---|
| binary | `fixtures/stack-overflow-01/vuln.elf` | `705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26` |
| contract | `fixtures/stack-overflow-01/contract.json` | `856b6ad2dabf69b705836f3a7c6466b534034cb1a4770a43f3fb596a11ce578c` |
| corpus | `fixtures/stack-overflow-01/cases/cases.json` | `fae5efd054358d16610987f5645eadc582ce53ac12debeb356941d6617ceec3d` |

The audit ran on these frozen bytes. The contract and corpus hashes match the G1
record and `fixtures/stack-overflow-01/SHA256SUMS`; nothing was re-frozen and no
criterion was edited to make a plan look better.

## 2. Audit provenance

- Provider/model: DeepSeek `deepseek-v4-pro`, temperature 0, fixed prompt
  `prompts/fix-plan.v1.md`.
- Prompt hash, identical for all three runs:
  `fb85f91c5b66f048820b3e6cc0eb2ad536c5fea1643ca155e8e0a5c9708fe407`.
- Three independent runs; every output kept, nothing retried away. Raw responses
  (key removed) are stored under `docs/audit/raw/`.
- Each plan's identity is bound by the runner, not by the model: `fixture_id =
  stack-overflow-01`, `contract_sha256 = 856b6ad2…`, `plan_id = plan-<sha prefix>`,
  `model.provider = deepseek`.
- M4 ran the audit on their own host with their own provider key (the key appears in
  no prompt, report, repository or CI log). This is the re-run with the merged #42
  harness: the earlier unbound set from the first #41 push stays in git history as
  tooling validation only and is **not** cited as evidence.
- Recorded by the provider: total tokens 24034 / 26858 / 20836 for runs 1 / 2 / 3.

## 3. Evidence hashes (SHA-256 of the committed files)

| Artifact | SHA-256 |
|---|---|
| `docs/audit/2026-11-21-audit-01.md` | `3f7c03327ac5b5d33b280e7aa830fb59a995b3d291d1183bc36dcc582ea772eb` |
| `docs/audit/2026-11-21-audit-01.json` | `00c49e41dac1e1fbe524338702986e6d5d0d223d0ea5338648336cca2bc774a0` |
| `docs/audit/fix-plan-v1.json` | `be2401a6210e3d7a7ef9f42fc26e466bf5400a2955dda05a8c95f81c525c9056` |
| `docs/audit/raw/run-1.json` | `0a5e3c5b4ddfcca02b07bc5e89e551ccba158125a56a887b989359a0edae6af0` |
| `docs/audit/raw/run-2.json` | `c1830a61ba628a824ae19319e2ee44f1072e365108ec273ecb01ba327435dee6` |
| `docs/audit/raw/run-3.json` | `0bccb1df9cd4af43df69634f4b64fcd09c650e1099b7ef9fb3a75f5606123f44` |

## 4. Three-run table

| Run | schema_valid | plan_sha256 | M1 | M5 | Critical errors | Usable |
|---|---|---:|---:|---|---|---|
| 1 | true | `9b117f09cdf1a1df8c37a751060c025b5cd1fc79e61729360f300373bbbd3fd9` | 98 | — | none | true |
| 2 | true | `c16d97ba9bc09a99211e1c73dd7039a2dd68fba39d7c5c5a692116e43030efb9` | 99 | 100 | none | true |
| 3 | true | `c5f2f1b361dd75f00622640903ec56e1c9a197665f2ef58353e0ee6c65895a7e` | 96 | — | none | true |

M1 scored all three runs on the rubric (contract/evidence). M5 scored the selected
plan with the implementability scorer (15/15, `audit_report_m5 = 100`,
`critical_error = false`; passed `redirect_at_patch_site`, `cave_in_reserved_range`,
`guard_byte_budget`, `rel32_reachable`, `no_structural_escape`, `manifest_self_check`).
Runs 1 and 3 were not independently scored by M5; this is recorded rather than hidden.

## 5. Selected plan

- `run_index`: 2 — `plan_sha256 = c16d97ba9bc09a99211e1c73dd7039a2dd68fba39d7c5c5a692116e43030efb9`
- Stored as `docs/audit/fix-plan-v1.json`, exactly as returned by the harness.
- Strategy: one 5-byte relative `call` at `0x401194` (the unbounded `strcpy`) is
  redirected to a 90-byte guard stub at `0x401220` in the reserved R-X tail. The stub
  bounds the source to 31 bytes and printable ASCII (`0x20..0x7e`); on violation it
  writes the exact 42-byte `invalid_stderr` to fd 2 and exits 1, otherwise it
  tail-jumps to `strcpy@plt` so the valid path is unchanged.
- Inside `allowed_edits`: one 5-byte redirect; code 90 B (<=256); data 42 B (<=64);
  no new segment, no new dynamic import or PLT/GOT entry, no text relocation, no W+X;
  RIP-relative data only.

## 6. Reviewer scores and decision

- M1 (contract/evidence): 99 (selected plan; 98 / 99 / 96 for runs 1-3)
- M5 (implementability): 100 (selected plan only)
- Resolved: 100 (round of the mean of 99 and 100)

**Decision: `proceed`.** Per `docs/plan/03-fixture-and-ai-audit-spec.md` section 6.7, at
least one plan scores >= 80 with no critical error (run 2, resolved 100) and M5 confirms
it is implementable. P3 starts: M5 implements the selected plan; the deterministic
verifier decides correctness at G3.

`correctness_established = true` in the machine report follows the section 6.5
plan-level definition (the plan covers every stated criterion and the proposed
verification distinguishes fixed from broken). It is not a binary verdict.

## 7. M1 verification performed (static only — no ELF executed on the host)

1. Call site `0x401194` really holds `e8 c7 fe ff ff` (call `0x401060` = `strcpy@plt`);
   code after the call (`0x401199: lea rax,[rbp-0x20]`) re-derives the buffer, so a stub
   may clobber `rsi`/`rdi`.
2. The reserved tail `0x401211-0x402000` is all zero (3567 bytes); every proposed
   code/data address lies inside it.
3. Each stub disassembles as claimed: redirect targets `0x401220`, data references
   resolve (`0x4012C0` / `0x401280` / `0x401260`), all three write the exact 42-byte
   `invalid_stderr`, and the 0..31 vs >=32 cutoff is correct.
4. Sizes, syscall usage, RIP-relative data and the single 5-byte redirect match
   `allowed_edits`; no new import, no new segment, no text relocation, no W+X.
5. Corpus fit: valid `""`, `A`, `hello`, 31 `A`, `a-b_c.9` keep `stdout = argv[1] + "\n"`
   and exit 0; invalid `32/33/64/128` `A` produce exit 1, empty stdout and the exact
   stderr.

## 8. M3 corpus consultation

The contract and corpus hashes were compared with the G1 record and `SHA256SUMS`
(unchanged). M3 (fixture/corpus owner) was notified on the gate PR for consultation
before signing; no corpus change was reported. M3 does not score the plans, per the
spec.

## 9. What G2 does not claim

- No candidate binary was produced, applied or executed at G2. `V0-V4`, the verdict and
  `verified_against_stated_criteria` are `not_run` until G3.
- One fixture, one model, three runs, same-team review. A usable plan is not evidence
  that a patch is correct.
- The model's explanations are untrusted display data. Only the selected plan was
  reviewed in depth, and its implementability was checked statically by M5.
- The earlier unbound audit set from the first #41 push is kept in git history as
  tooling validation only and is not evidence.

## 10. Signature

Gate G2 is signed off on the evidence above.

- M1 `@leesirleesirlee-star`, 2026-11-21
