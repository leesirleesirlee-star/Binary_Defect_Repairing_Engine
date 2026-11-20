# Preflight report — official main fixture

Status: **structural dry-run preflight on the fixture merged in `main`**. This is
not a verdict, not a candidate and not evidence of runtime correctness.

## 1. Base information

| Field | Value |
|---|---|
| Main commit | `2cb4f1d` (fixture freeze); G1 record `f90f5f3` |
| Fixture path | `fixtures/stack-overflow-01/vuln.elf` |
| Fixture SHA-256 | `705ab9290094218af7164fb6415cde14bd800b040d52f3fc1e9d1b766b3d9c26` |
| Fixture size | 16016 bytes |
| Reserved range | `0x401211`–`0x402000` |
| Patch site | `0x401194` (file offset `0x1194`) |
| `strcpy@plt` | `0x401060` |
| Tool/version | `m5-validate-fixture 0.1.0-dryrun` |
| Run timestamp (UTC) | `2026-11-20T14:02:59Z` |
| Operator | M5 agent |

The fixture hash matches `fixtures/stack-overflow-01/fixture-manifest.json`.

## 2. Command

```bash
python -m pipeline.repair.validate_fixture \
  --elf fixtures/stack-overflow-01/vuln.elf \
  --start 0x401211 --end 0x402000 \
  --patch-site 0x401194 --strcpy-plt 0x401060 \
  --manifest-out var/official-preflight-manifest.json \
  --out var/official-preflight-report.json
```

## 3. Execution stages

| Stage | Result |
|---|---|
| `parse_elf` | ok |
| `patch_site_preimage` | ok (`e8c7feffff`) |
| `cave_finder` | ok (`0x401220`, 3552 bytes) |
| `rel32_reachability` | ok |
| `patch_manifest` | ok (`11f61c17...`) |
| `write_manifest` | ok (JSON only) |
| `self_check` | `checks_passed` |

## 4. Result

```text
status: dry_run_checks_passed
exit_code: 0
```

No exception condition occurred.

## 5. Manifest and invariants

| Item | Value |
|---|---|
| Manifest | `var/official-preflight-manifest.json` (generated, not committed) |
| `manifest_sha256` | `11f61c171ca5a365a4b4ff99765225864bf6921bda4640b917f23cda65a9820b` |
| Cave | `0x401220`, code 69 + data 42 = 111 bytes |
| Patch bytes | `e887000000` (call rel32 135) |
| `preview.candidate_sha256_if_applied` | `16fefa50c2e4a6d07410e7582bbf370b638b93ccfa612d30432cd21f14e04258` |
| `preview.candidate_written` | `false` |
| `verdict` | `null` |
| Headers / entry / PT_LOAD count / flags | unchanged |
| No new segment / no W+X / `.dynamic` unchanged / no new import | true |
| Changed bytes covered | true (`edit_count=2`, `changed_byte_count=96`) |
| Reversibility | inverse edits restore `705ab929...9c26` |
| `self_check` | `checks_passed` |

## 6. Attachments

- Full JSON report: `var/official-preflight-report.json` (local, generated)
- Dry-run manifest: `var/official-preflight-manifest.json` (local, generated)
- Golden/reversibility/determinism suites: `tests/repair/`

## 7. Boundary statement

This is a structural dry-run preflight only. `dry_run_checks_passed` does not mean
the repair is correct, does not create a candidate and does not write a verdict.
M3's guest and verifier remain the only source of runtime correctness and the
verdict.

The default manifest is still the provisional `m5-dryrun-v0` shape; the
`EditManifestV1` opt-in mapping is landed but not used by this preflight.
