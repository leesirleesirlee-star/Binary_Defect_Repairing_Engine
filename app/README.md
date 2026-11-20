# `app` - FastAPI + Jinja GUI

> **S1 shell:** the v1.2.2 conversation UI is copied unchanged under
> `app/static/ui/` and served by `app.main` for visual review only. See
> [`STATIC-SHELL.md`](STATIC-SHELL.md). The plan is
> [`docs/gui/conversation-console-plan.md`](../docs/gui/conversation-console-plan.md).
# `app` - FastAPI + Jinja GUI

Owner: M2 (`gui` module). Gate: G4.

## Four screens

1. **Task** - fixture identity, hashes, contract revision, run button.
2. **Analysis** - disassembly view, finding, AI plan card with assumptions and
   uncertainties, human approve control.
3. **Verification** - original vs candidate case table, 31/32 boundary, verdict
   banner.
4. **Evidence** - artifacts, hashes, downloads, limitations.

## Rules

- The GUI **renders persisted JSON**. It never computes a verdict, a pass rate or
  a success label. Any success label that originates in a template or route is a
  defect.
- `not_run`, `unverified`, `timed_out` and missing artifacts are shown verbatim.
- Chinese UI labels; data fields, hashes, JSON and verdict labels stay English
  ASCII.
- Reuse the archive's visual assets (`app/templates`, `app/static`) and adapt the
  routes; do not copy the old backend.
- The GUI does not import `pipeline.verify`, `pipeline.repair` or `pipeline.ai`.
- No client data, key or private log in the browser.

## G0 read-only data layer (issue #3)

The GUI renders persisted JSON; it does not import `pipeline.verify`,
`pipeline.repair` or `pipeline.ai`, and it never computes a verdict or success
label.

`app/loader.py` exposes:

```python
from app.loader import load

document = load("app/examples/example.json")
```

`load()` reads a regular JSON object below the repository data root. It rejects
absolute paths outside the root, `..` escapes, NUL bytes, non-`.json` files and
symlink escapes. A missing file raises `ArtifactMissing` so the presentation
layer can render `missing`, not success.

`app/render.py` is the shared honesty boundary for the future four screens. It
renders observation statuses verbatim, missing values as `missing`, and a
verdict only from a persisted `outcome`. `verified_against_stated_criteria`
never appears unless the persisted verdict contains it.

The four screens themselves remain deferred to #12. The schema field review and
the `not_run` items are recorded in `docs/gui/schema-review.md`.
