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
- The four screens share one layout and one CSS entry point; a page that forks
  the layout is a review blocker.
