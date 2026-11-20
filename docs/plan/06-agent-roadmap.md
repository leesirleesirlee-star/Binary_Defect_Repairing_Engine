# 06 - Agent roadmap: from the MVP2 evidence chain to an automated repair agent

**Status:** direction, not a commitment. No schedule is attached to any stage.
**Owner:** M1 (contract and integration). **Consumers:** M2-M5.
**Scope note:** this document describes the product that comes after MVP2. It does
not change MVP2's scope, gates or delivery. MVP2's out-of-scope list
(`00-mvp2-roadmap.md` section 4) still applies to MVP2.

## 1. What the product is

An agent that receives a broken x86-64 ELF and a behaviour suite, repairs the
binary, verifies the candidate against that suite in the guest, and exports the
candidate. No human is required at run time.

| | Content |
|---|---|
| **Input** | the ELF; positive cases (input -> expected stdout, stderr, exit); negative cases (input -> observed wrong behaviour, at least one of which reproduces the defect); optional one-line defect description |
| **Output** | `candidate.elf`, `edit-manifest.json`, `verdict.json`, `evidence-bundle.json`; the input file is never modified |
| **Not input** | source code, debug symbols as a requirement, a human-written contract, network access, provider keys inside the guest |

The product may refuse. Refusal is a result, not a failure of the run.

## 2. The one rule that keeps the product honest

The oracle is the supplied data, not the model and not a reviewer.

- The contract is **derived deterministically** from the supplied cases plus the
  disassembly, written to `contract.json`, and hashed. The model may propose a
  reading of the evidence; it may not invent a criterion that no case exercises.
- Every criterion in the contract names the case or the static fact that
  establishes it. A criterion with no witness does not enter the contract; the
  corresponding check is `not_run` and the verdict cannot be a success.
- The verdict vocabulary is unchanged (`00-mvp2-roadmap.md` section 5). There is
  exactly one success label, `verified_against_stated_criteria`, and it means
  "every criterion passed on the supplied suite, on matching hashes" - never
  "the program is fixed".
- Coverage is reported next to the verdict: which cases ran, which behaviours are
  unmeasured, which parts of the binary the patch touches.

## 3. Pipeline

```text
ELF + cases
   |
   v
[1] intake and triage          crash / wrong-output / unknown; reject unsupported input
   |
   v
[2] localisation               crash site -> function -> copy site -> buffer and frame
   |
   v
[3] contract derivation        cases -> criteria, each with a witness; hashed
   |
   v
[4] plan                       model proposes the edit against the contract and the edit budget
   |
   v
[5] patch                      byte-level edit inside the allowed region; manifest recorded
   |
   v
[6] verify                     guest runs the full suite on original and candidate; V0-V4
   |
   +--> fail: loop to [4] within the iteration budget, with the failure attached
   |
   v
[7] export                     candidate + manifest + verdict + evidence bundle
```

Steps [1], [2], [3], [6] are deterministic. Only [4] calls a model. Step [5] is a
deterministic tool that applies the planned edit; it never decides what to edit.

## 4. Capability levels

Levels describe what the agent can accept, not when it will be built. A level is
entered only when the previous level's acceptance record exists.

| Level | Input it can accept | What is new | Verdict reachable |
|---|---|---|---|
| **L0** | the frozen MVP2 fixture; human-frozen contract; symbols present; reserved executable tail | nothing - this is MVP2 | `verified_against_stated_criteria` on the L0 contract |
| **L1** | same fixture family; contract derived from cases; symbols present; reserved tail | contract derivation, iteration loop, export | same, with `criteria_source: derived_from_cases` |
| **L2** | binaries without a reserved tail | cave finding, or segment extension with its own proof; structure checks | same, provided the structural invariant holds |
| **L3** | stripped binaries | localisation without symbols: function boundaries from `.eh_frame` or prologue scanning, stack unwinding from the crash, inference of the copy site and buffer offset, confirmed by mutating the failing case | same, with explicit unmeasured fields where symbols would have helped |
| **L4** | defect classes beyond a crashing memory-safety bug | not designed here | `unsupported` until designed |

L4 is deliberately undefined. A wrong-output defect has no crash site to anchor
localisation, so it needs a different design, not a bigger prompt.

L3 is required, not optional. Released binaries are normally stripped, so a repair
product that only accepts symbol-bearing samples is a development tool. L3 sits
last because it is the hardest localisation problem, not because it can be
skipped: contract derivation, patching and verification are unchanged, but
localisation must be established from behaviour and structure instead of names.
L4 (non-crashing defects) stays out of scope until L3 has an acceptance record.

L2 revisits an option that MVP2 rejected: ADR 0001 refused segment extension for
the MVP2 fixture because the fixture could reserve its tail at build time. In the
product there is no build step to lean on, so cave finding and segment extension
are both legitimate, provided the verifier proves the structural change (no new
segment, no permission change, same mapping page).

## 5. Contract derivation

Deterministic rules, in order. Each criterion is written with a `witness` field
naming the case or the static fact that establishes it.

| Criterion | Derived from | If missing |
|---|---|---|
| negative case must not crash | every negative case that crashed the original | the criterion is omitted; the check is `not_run` |
| negative case must produce the stated rejection | a negative case whose expected response is supplied | omitted, not guessed |
| positive cases keep stdout, stderr and exit exactly | every positive case, run on the original first | the case is unmeasured; coverage shrinks |
| no write past the destination | disassembly of the copy call and the frame layout | `unverified`; a static criterion cannot be asserted without the static fact |
| patch stays inside the allowed region | the edit budget and the reserved range or cave | no legal region at all: `unsupported`; a plan that does not fit: `rejected` |

The first task on intake is to run the positive cases on the **original** binary
and record what they actually do. A positive case the original already fails is
not a regression case; it is reported and excluded, not repaired.

## 6. Anti-overfit rules

An agent that iterates against a fixed suite will eventually fit the suite. These
rules are part of the design, not a testing nicety.

1. **Holdout.** The agent receives a training split. The verifier runs a holdout
   split the agent never sees, plus mutated variants of the negative cases
   (length and content variations around the boundary).
2. **Structural constraint.** The patch must land at or near the defect site, must
   not add input-specific branches, and must not make an undeclared change to
   program headers or section headers. L2 may declare exactly one structural
   change, and the verifier must prove it. A patch that special-cases a case is
   rejected by structure, not by opinion.
3. **Behavioural equivalence.** Positive cases are compared byte for byte on
   stdout, stderr and exit code against the original's recorded behaviour.
4. **Locality.** The changed byte set must match the manifest exactly; any other
   difference is `unverified`.
5. **Re-apply.** The manifest, applied to a clean copy of the original, must
   reproduce the candidate hash.

## 7. Iteration loop and budget

- The loop runs at most `max_attempts` patch attempts and `max_runs` guest
  executions. These are configuration values recorded in the evidence bundle.
- An attempt may only be called an improvement if the full training suite ran.
  Partial runs are recorded as `not_run`, never as progress.
- Every attempt is recorded: plan, edit, suite result, reason for rejection. The
  audit trail is the deliverable, not the final file alone.
- The loop stops on: success, budget exhaustion, an unsupported input, or a
  structural violation that cannot be repaired within the budget. Each stop
  state maps to a verdict, never to silence.

## 8. Refusal and degraded results

| Situation | Result |
|---|---|
| architecture or format outside scope | `unsupported` |
| no negative case reproduces the defect | `unsupported` |
| no positive case supplied | allowed, but coverage is empty for regressions: the contract holds only crash criteria, the verdict may pass only those, and the coverage line says so |
| a case is flaky on the original | `unverified`; flakiness is reported, not averaged away |
| guest unavailable or timed out | `unverified` |
| budget exhausted with no passing candidate | `rejected` plus the last failure |
| training suite passes but a holdout or mutated case fails | `rejected`; the overfit is recorded |
| patch requires a structural change outside the allowed region | `unsupported` |

## 9. Safety invariants

- The input ELF is opened read-only and never modified. The candidate is a new
  file.
- The candidate executes only in the guest, never on the host, never with network
  access, never with credentials.
- The provider key stays in the host process; the guest and the model never see
  the source, the corpus internals or the key.
- The agent may export a candidate and a verdict. It may not install, run or
  promote it on a real system.

## 10. Relation to MVP2

MVP2 is L0 and remains the reference implementation of the evidence chain. The
agent replaces exactly two things:

1. the human who writes `contract.json` - replaced by derivation from cases;
2. the human who reads a failed run and decides what to try next - replaced by the
   iteration loop.

Everything else is reused unchanged: the guest harness, `ObservationV1`, the
V0-V4 checks, the verdict vocabulary, the evidence bundle, the "no claim beyond
scope" rule. MVP2's hand-written contract stays in the repository as the L0
baseline and as the ground truth for evaluating the derivation step: the L1 agent
must reproduce that contract from the cases before it is trusted.

## 11. What changes in the repository when implementation starts

| Artifact | Change |
|---|---|
| `schemas/` | `ContractV1` gains `criteria_source` and per-criterion `witness`; `VerdictV1` unchanged; `EvidenceBundleV1` gains attempt history and coverage |
| `modules.json` / `CODEOWNERS` | new module for the orchestrator and the iteration loop; path decision recorded in an ADR before code lands |
| `pipeline/` | new orchestrator package; `analyze`, `ai`, `repair`, `verify` keep their current ownership |
| `guest/` | suite runner accepts a case set and a candidate, returns per-case results |
| tests | holdout and mutation suites, structural rejection tests, budget-exhaustion tests |

No module is added now. The entry is a contract change and an ADR, not a
directory created ahead of its owner.

## 12. Open questions

1. How much localisation can be done without symbols before L3 becomes a research
   project rather than a product step?
2. When the user supplies no positive cases, should the product refuse, or accept
   with an explicit "crash-only" scope? The vocabulary allows the latter; the
   honest default is to say it in the verdict, not to hide it.
3. How should multiple defects in one binary be handled: refuse beyond the first,
   or report partial coverage?
4. Reproducibility: two runs of the agent may produce different patches. Is the
   deliverable "a working candidate" or "a reproducible candidate"? The manifest
   and the re-apply check make the second possible; it should be the goal.

## 13. Non-goals

Route B (decompile and recompile), symbolic execution, formal verification,
multi-binary triage at scale, client binaries, network installation, and any
claim that a passing suite proves the program safe.

## Provenance

This replaces the pre-reset "F0" concept with route B removed. F0's structure
came from the archived v1.2.2 application; this roadmap keeps its honesty rules
and drops its module layout. No dates are attached on purpose: capability levels
are entered when the previous acceptance record exists, not when a calendar says
so.
