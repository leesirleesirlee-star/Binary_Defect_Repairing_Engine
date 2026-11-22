# S4/S5 dependency blockers

- **S4 audit** requires #36 (`feat/audit/9-harness-rubric`, open) and #34
  (`feat/ai/8-prompt-transport`, open). The GUI renders preview rows only;
  `audit_runs` is labelled synthetic and `usable` is always false in preview.
- **S5 repair** requires #28 (`m5/edit-manifest-v1-cli`, open). The GUI supports
  `file_change` manifest/diff payloads, but no real dry-run or applied candidate
  exists.
- **S5 verify** requires #11. The GUI supports `verification.check` rows and a
  full VerdictV1 card, but no persisted verdict exists; `not_run` and `null`
  remain visible and are never converted to success.
- **S6** can show real analysis artifacts and export bundles; repaired ELF,
  audit report, manifest and verdict downloads remain unavailable until S4/S5.
