# Preflight report template (M5 dry-run)

Status: **template only**; fill it only after M3 publishes the new fixture and
PR #14 / ADR 0001 is in `main`. This is a structural report, not a verdict.

## 1. Base information

| Field | Value |
|---|---|
| Fixture path | `{{fixture_path}}` |
| Fixture SHA-256 | `{{fixture_sha256}}` |
| Reserved range | `{{start}}` – `{{end}}` |
| Patch site vaddr | `{{patch_site_vaddr}}` |
| Patch site file offset | `{{patch_site_file_offset}}` |
| `strcpy@plt` vaddr | `{{strcpy_plt_vaddr}}` |
| Tool/version | `m5-validate-fixture {{tool_version}}` |
| Git commit | `{{git_commit}}` |
| Run timestamp (UTC) | `{{run_timestamp_utc}}` |
| Operator | `{{operator}}` |

## 2. Command

```bash
python -m pipeline.repair.validate_fixture \
  --elf {{fixture_path}} \
  --start {{start}} \
  --end {{end}} \
  --patch-site {{patch_site_vaddr}} \
  --strcpy-plt {{strcpy_plt_vaddr}} \
  --manifest-out {{manifest_path}} \
  --out {{report_path}}
```

Do not substitute a different patch site or widen the range to make the check
pass.

## 3. Execution stages

| Stage | Expected | Measured | Status |
|---|---|---|---|
| `parse_elf` | ELF64 x86-64 `ET_EXEC` | `{{elf_class_machine_type}}` | `{{parse_status}}` |
| `patch_site_preimage` | 5-byte `E8` call at approved site | `{{patch_site_bytes}}` | `{{patch_status}}` |
| `cave_finder` | zero cave >= 111 bytes, aligned | `{{cave_vaddr}}`, size `{{cave_size}}` | `{{cave_status}}` |
| `rel32_reachability` | call site +5 → cave fits int32 | `{{rel32_delta}}` | `{{rel32_status}}` |
| `patch_manifest` | dry-run JSON only | `{{manifest_sha256}}` | `{{manifest_status}}` |
| `self_check` | structural invariants pass | `{{self_check_status}}` | `{{self_check_status}}` |

## 4. Result

```text
status: {{status}}
exit_code: {{exit_code}}
```

Allowed status values:

- `dry_run_checks_passed` — structural checks passed; **not a verdict**;
- `no_candidate` — no cave meets the requested size/alignment; include
  `max_zero_run={{max_zero_run}}`;
- `unsupported` — range, segment, patch shape or rel32 is not applicable;
- `error` — malformed input, measured preimage mismatch, or IO failure;
- `dry_run_checks_failed` — one or more structural invariants failed; list every
  failed check.

If `no_candidate`, attach the largest available zero run and the requested
`min_size`. If `error`, attach the measured bytes or parser message. Do not
retry with relaxed rules.

## 5. Manifest and invariants

| Item | Value |
|---|---|
| Manifest path | `{{manifest_path}}` |
| `manifest_sha256` | `{{manifest_sha256}}` |
| `original.sha256` | `{{original_sha256}}` |
| `preview.candidate_sha256_if_applied` | `{{preview_candidate_sha256}}` |
| `preview.candidate_written` | `false` |
| `verdict` | `null` |
| Headers unchanged | `{{headers_unchanged}}` |
| Entry unchanged | `{{entry_unchanged}}` |
| PT_LOAD count/flags unchanged | `{{pt_load_unchanged}}` |
| No W+X / no new import | `{{no_wx_no_import}}` |
| Changed bytes covered | `{{changed_bytes_covered}}` |
| Reversibility restored hash | `{{restored_sha256}}` |
| Reversibility matches original | `{{reversibility_matches}}` |

## 6. Attachments

- Full JSON report: `{{report_path}}`
- Dry-run manifest: `{{manifest_path}}`
- `self_check` output: `{{self_check_summary}}`
- Tool version output: `{{version_output}}`

## 7. Boundary statement

This report is a **dry-run structural preflight**. A `dry_run_checks_passed`
result does not mean the repair is correct, does not create a candidate and does
not write a verdict. Runtime correctness belongs to M3's guest and verifier.

If the result is not `dry_run_checks_passed`, follow
`fixture-exception-handling.md` and report the measured values to M1/M3/M4; do
not change the fixture, contract or check rules to force a pass.
