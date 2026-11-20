# Migration manifest: what to bring from the old project, and what to leave

**Status:** proposal, 2026-11-20
**New repository:** <https://github.com/leesirleesirlee-star/Binary_Defect_Repairing_Engine> (empty)
**Archive repository:** <https://github.com/leesirleesirlee-star/Binary_Repair> (v1.2.2)
**Local old checkout:** `D:\BinaryRepair_Project` (an older branch; **not** the authority)

This file exists so that a person or agent who opens the new folder knows:

- which documents are current;
- which old documents and files are worth importing;
- which old code, evidence and claims must **not** cross the boundary;
- how to import something without recreating the old tangle.

## 1. The rule

> Copy **documents and visual assets** deliberately. Do **not** copy the old
> application architecture, old evidence, old route code or old acceptance
> claims. MVP2 has a different evidence chain and a smaller scope.

The old repository is a successful, larger project. Reusing its **lessons** is
useful. Reusing its **structure** would import the exact complexity MVP2 is
trying to remove.

## 2. Current vs archive

| Document set | Status | Where |
|---|---|---|
| `docs/plan/00`-`04` | **current authority** for scope, ownership, GitHub and modules | this folder |
| `START-HERE.md`, `README.md`, `AGENTS.md` | **current authority** for onboarding and rules | this folder |
| `docs/MIGRATION.md` (this file) | **current authority** for imports | this folder |
| `modules.json` | **current authority** for module ownership | this folder |
| v1.2.2 `docs/overview/product/*` | reference: product rationale and research | archive |
| v1.2.2 `docs/acceptance/LIMITATIONS.md` | reference: what the old project did **not** prove | archive |
| v1.2.2 `docs/status/final-status.md` | reference: old status vocabulary | archive |
| v1.2.2 `docs/architecture/*` | reference: old controller/agent design | archive |
| v1.2.2 `docs/development/handoffs/*` | history, **not** current evidence | archive |
| v1.2.2 `artifacts/**` | old evidence, **not** MVP2 evidence | archive |

If a conflict exists between this folder and the archive, **this folder wins**.

## 3. Import table

### 3.1 Documentation (M1 imports, into `docs/archive/v1.2.2/`)

| Old path (v1.2.2) | New destination | Action | Why |
|---|---|---|---|
| `docs/overview/product/PRD-BinaryRepair-MVP.md` | `docs/archive/v1.2.2/product/PRD.md` | copy | product scope and outcome semantics |
| `docs/overview/product/TechDesign-BinaryRepair-MVP.md` | `docs/archive/v1.2.2/product/TechDesign.md` | copy | architecture rationale, V0-V5 ladder |
| `docs/overview/product/research-BinaryRepair.md` | `docs/archive/v1.2.2/product/research.md` | copy | source register and background |
| `docs/overview/product/verification-design.md` | `docs/archive/v1.2.2/product/verification-design.md` | copy | verification reasoning |
| `docs/acceptance/LIMITATIONS.md` | `docs/archive/v1.2.2/LIMITATIONS.md` | copy | honest limits; must not be lost |
| `docs/acceptance/ACCEPTANCE.md` | `docs/archive/v1.2.2/ACCEPTANCE.md` | copy | old acceptance record, history only |
| `docs/status/final-status.md` | `docs/archive/v1.2.2/final-status.md` | copy | old result vocabulary, history only |
| `docs/architecture/agent-console.md` | `docs/archive/v1.2.2/architecture/agent-console.md` | copy | GUI flow ideas for M2 |
| `docs/architecture/host-importer-broker.md` | `docs/archive/v1.2.2/architecture/host-importer-broker.md` | copy | guest boundary lessons |
| `docs/architecture/code-repair.md` | `docs/archive/v1.2.2/architecture/code-repair.md` | copy | pasted-source feature, out of MVP2 scope |
| `docs/reference/buffer-overflow-patterns.md` | `docs/archive/v1.2.2/reference/buffer-overflow-patterns.md` | copy | C patterns for M3/M5 |
| `docs/reference/patch-validation.md` | `docs/archive/v1.2.2/reference/patch-validation.md` | copy | scope model for M5 |
| `docs/development/repository-layout.md` | `docs/archive/v1.2.2/reference/old-repository-layout.md` | copy | explains the old tree; not the new one |
| `docs/reference/interfaces/*` | `docs/archive/v1.2.2/reference/interfaces/` | copy | old protocol; readable, not binding |

Do **not** copy `docs/development/handoffs/**` one by one. If the team wants the
history, link the archive repository; the new folder keeps only the curated set
above.

### 3.2 GUI visual assets (M2 imports, into `app/`)

| Old path (v1.2.2) | New destination | Action | Why |
|---|---|---|---|
| `app/templates/base.html` | `app/templates/base.html` | copy, then adapt | page shell, nav, theme boot |
| `app/templates/landing.html` | `app/templates/landing.html` | copy, then adapt | landing page |
| `app/templates/agent.html` | `app/templates/agent.html` | copy, then adapt | terminal/agent console look |
| `app/templates/report.html` | `app/templates/report.html` | optional | evidence/report layout reference |
| `app/templates/evidence.html` | `app/templates/evidence.html` | optional | evidence table reference |
| `app/static/css/agent.css` | `app/static/css/agent.css` | copy | console styling |
| `app/static/css/app.css` | `app/static/css/app.css` | copy | base styling |
| `app/static/css/ds.css` | `app/static/css/ds.css` | copy | design tokens |
| `app/static/css/workbench.css` | `app/static/css/workbench.css` | copy | workbench layout |
| `app/static/js/*.js` | `app/static/js/` | copy selectively | UI behavior; remove old API calls |

The GUI is **visual reference plus reusable CSS**, not a working frontend for
MVP2. It calls old endpoints and old data shapes. M2 rewrites the routes and the
data binding; the four-screen flow is in `docs/plan/00-mvp2-roadmap.md`.

### 3.3 AI transport (M4 imports, into `pipeline/ai/transport/`)

| Old path (v1.2.2) | New destination | Action | Why |
|---|---|---|---|
| `binaryrepair_ai/client.py` | `pipeline/ai/transport/client.py` | copy, then adapt | HTTP client, retries, timeouts |
| `binaryrepair_ai/errors.py` | `pipeline/ai/transport/errors.py` | copy | typed failures |
| `binaryrepair_ai/settings.py` | `pipeline/ai/transport/settings.py` | copy | env/config handling |
| `binaryrepair_ai/pricing.py` | `pipeline/ai/transport/pricing.py` | optional | token cost recording |
| `binaryrepair_ai/schemas.py` | **do not copy** | - | old candidate schema; MVP2 uses `FixPlanV1` |
| `binaryrepair_ai/prompts.py` | **do not copy** | - | old prompts; M4 writes the new disassembly-only prompt |
| `binaryrepair_ai/provider.py` | **do not copy** | - | old provider flow; adapt the client instead |

The transport is reusable; the **contract** it serves is not.

### 3.4 Reference fixture (not imported)

| Old path | Action | Why |
|---|---|---|
| `fixtures/public/CWE121_src_char_declare_cpy_51b/` | reference only | a 50-byte Juliet fixture with a different contract; MVP2 builds a simpler 32-byte sample |
| `routea/`, `routeb/`, `workers/`, `tools/` | reference only | old route implementations; MVP2 has one new trampoline route |
| `artifacts/**` | **do not copy** | old evidence; it cannot support an MVP2 verdict |
| `plugins/`, `knowledge/`, `data/` | **do not copy** | out of scope for MVP2 |

If the team later wants a second fixture for comparison, import it as
`fixtures/reference/` with its own manifest and no old verdict.

## 4. What must not cross the boundary

| Item | Why |
|---|---|
| Old `app/backend.py`, `app/controller_api.py`, `app/services/**`, `app/domain/**`, `app/db/**` | a different architecture with six roles and a DB; MVP2 uses a thin API and JSON artifacts |
| Old `tests/**` wholesale | they test the old code and old claims; importing them invites false green |
| Old `artifacts/**` and `SHA256SUMS` | they bind to the old fixture and old candidate; never cite them as MVP2 evidence |
| Old acceptance verdicts (`success_within_scope`) | MVP2 uses `verified_against_stated_criteria`; do not mix vocabularies |
| Source C from the old fixture | MVP2's source separation is per fixture; do not let an old source path leak into the new prompt |
| Any client binary, key, private log | never in the repository or a model prompt |

## 5. How to import safely

1. Take the file from a **tag or commit**, not from a working tree:
   `git show <archive-tag>:<path> > <destination>`.
2. Record in `docs/archive/v1.2.2/IMPORT.md`:
   - source repository and commit SHA;
   - source path and destination;
   - SHA-256 of the imported bytes;
   - who imported it and why.
3. Mark the imported file read-only in spirit: do not edit it in place. If MVP2
   needs a changed version, copy it into the owning module and adapt there.
4. Do not copy an old claim into a new document without the word "archive" and
   the old scope next to it.
5. Run `python scripts/check_modules.py` after the import; the destination must
   belong to the importing module.

## 6. Mapping old folders to new folders

| Old v1.2.2 | New MVP2 | Note |
|---|---|---|
| `app/templates`, `app/static` | `app/` | visual assets only |
| `binaryrepair_ai/` | `pipeline/ai/transport/` | transport only |
| `routea/`, `routeb/` | `pipeline/repair/` (new design) | do not copy the old routes |
| `workers/` | `guest/` | new runner |
| `fixtures/public/` | `fixtures/stack-overflow-01/` | new sample |
| `artifacts/` | not imported | old evidence |
| `docs/overview/` | `docs/archive/v1.2.2/product/` | reference |
| `docs/reference/` | `docs/archive/v1.2.2/reference/` | reference |
| `docs/acceptance/` | `docs/archive/v1.2.2/` | history |
| `docs/development/` | archive link only | not copied |
| `docs/showcase/` | `docs/gui/reference/` | screenshots for M2 |

## 7. Checklist for the person opening the new folder

- [ ] I can explain the MVP2 scope without reading the old repository.
- [ ] I know the contract and corpus are frozen before the AI audit (G2).
- [ ] I know the only success state is `verified_against_stated_criteria`.
- [ ] I know which old docs are current (this folder) and which are archive.
- [ ] I know which old code is **not** imported and why.
- [ ] I know my module in `modules.json` and my paths.
- [ ] I know the CI commands and the module label rule.
- [ ] I know the host must not execute the fixture or a candidate.

If any box is unchecked, read `START-HERE.md` and `docs/plan/00` again before
writing code.

## 8. Why this matters

The old project's hardest lesson was not "we need more code". It was:

> An AI that drafts the contract, the repair and the evaluation can produce
> agreement that is not evidence.

The migration therefore keeps the **documents that explain that lesson** and
drops the **architecture that produced the circularity**. That is the point of
this manifest.
