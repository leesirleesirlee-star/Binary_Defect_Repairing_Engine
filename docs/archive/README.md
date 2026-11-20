# Archive: curated v1.2.2 reference

This folder holds documents imported from the accepted v1.2.2 repository
<https://github.com/leesirleesirlee-star/Binary_Repair>. They are **history and
reference**, not current authority.

## What belongs here

The import table is in [`../MIGRATION.md`](../MIGRATION.md). Typical imports:

- product rationale, PRD and technical design;
- limitations and old acceptance record;
- buffer-overflow patterns and patch-validation notes;
- old repository layout and architecture notes;
- GUI reference screenshots.

## What does not belong here

- old `artifacts/**` or `SHA256SUMS` (they bind to the old fixture);
- old handoff records copied one by one (link the archive instead);
- old source code (import only the specific transport/visual files listed in
  `MIGRATION.md`);
- any client binary, key or private log.

## Import procedure

1. Take the bytes from a tag or commit, not a working tree:
   `git show <tag>:<path> > <destination>`.
2. Add or update `IMPORT.md` in this folder with:
   - source repository and commit SHA;
   - source path and destination;
   - SHA-256 of the imported bytes;
   - importer and reason.
3. Do not edit the imported bytes. If MVP2 needs a changed version, copy it into
   the owning module and adapt it there.
4. Run `python scripts/check_modules.py --base origin/main`; this folder belongs
   to `infra`.

## Authority

If an archive document and a current document conflict, the current document
wins. Do not cite an archive verdict as MVP2 evidence.
