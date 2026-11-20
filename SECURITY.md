# Security policy

## Scope

This repository is a research and course project. It repairs one public,
team-built fixture and does not accept arbitrary client binaries.

## Reporting

If you find a security issue in the project code, open a private report to the
maintainers rather than a public issue. Do not include a real client binary,
credential, private log or personal data in a report.

## Key handling

- The provider key lives only in the host process environment.
- It must never reach the browser, the guest, CI logs, the audit report or the
  repository.
- `.env` is gitignored; `.env.example` contains placeholders only.
- If a key is committed, rotate it first, then ask the maintainer to rewrite
  history. Deleting the file in a later commit is not enough.

## Binary handling

- The host never executes the fixture, a candidate or model-generated code.
- Execution belongs to the disposable guest with no network and no credentials.
- The original binary and the frozen corpus are read-only.
- A candidate must not change a later test's oracle.

## Supported versions

Only the current `main` is supported. The archived v1.2.2 repository is a
historical record, not a maintained branch.
