# Pipeline modules

The pipeline turns an ELF into evidence. Each subdirectory is a separate module
with its own owner, tests and gate. See `modules.json` for the registry.

```text
analyze ──> ai ──> audit ──> repair ──> verify ──> gui (renders)
   │                                         ^
   └──────────── contract ───────────────────┘
```

| Module | Owner | Input | Output | Must not |
|---|---|---|---|---|
| `analyze/` | M4 | ELF path, contract | `DisassemblyViewV1`, `FindingV1` | read `fixtures/**/build/` or call a model |
| `ai/` | M4 | disassembly view, contract | `FixPlanV1` | read the fixture, corpus or verifier |
| `audit/` | M4 | disassembly, plans, rubric | audit report | read the hidden corpus or score itself |
| `repair/` | M5 | approved plan, original ELF | candidate ELF, `EditManifestV1` | read the verifier or the corpus; patch before G2 |
| `verify/` | M3 | original, candidate, corpus, contract | `VerdictV1` | import the AI, audit or repair code |
| `gui/` (`app/`) | M2 | persisted JSON | rendered pages | compute a verdict or import verifier logic |

**Deterministic before model.** `analyze` and `verify` never call a model; `ai`
and `audit` never decide a verdict. This is the separation the reference report
requires.

Each submodule has a `README.md` with its interface. Do not add a cross-module
import without an ADR: the allowed directions are in `modules.json`.
