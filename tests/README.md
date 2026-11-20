# Tests

Host tests are static and fast. They never execute the fixture, a candidate or
model-generated code.

```bash
python -m pytest -q -m "not guest"
```

`guest` tests run only in the disposable guest and are reported as `not_run` on
the host. Layout:

- `tests/contract/` - schemas and result vocabulary (M1)
- `tests/fixture/` - build, corpus and runner (M3)
- `tests/verify/` - verdict checks (M3)
- `tests/analysis/` - disassembly and prompt separation (M4)
- `tests/repair/` - patch and edit manifest (M5)
- `tests/app/` - render and honesty (M2)
