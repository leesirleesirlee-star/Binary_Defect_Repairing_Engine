# `pipeline/repair` - cave finder, patch writer, edit manifest

Owner: M5 (`repair` module). Gate: G3.

## Input

- The original ELF.
- The approved `FixPlanV1` from G2.
- `ContractV1` (allowed edits).

## Output

- `candidate.elf`.
- `EditManifestV1`: every offset, vaddr, original bytes, new bytes and reason.
- A reproducible patch script.

## Rules

- **Do not apply a fix to the fixture before G2 approves a plan.** Generic ELF
  editing primitives and dry-run manifests are allowed during G1/G2.
- Only the edits in the approved plan and the contract: one 5-byte redirect, a
  cave in the existing R-X segment, no new segment, no new import, no W+X.
- The valid path must keep `strcpy` semantics and the return value; the invalid
  path writes the exact stderr line and exits 1.
- Never read `pipeline/verify/` or `fixtures/**/cases/`.
- The candidate is handed to M3; M5 does not sign the verdict.

## Dry-run tools (M5, current)

These are pure-Python, standard-library-only tools. They do not execute an ELF
and do not write a candidate.

```text
pipeline/repair/elf64.py        ELF64 header/segment/section/vaddr parser and
                                in-memory edit preview
pipeline/repair/guard.py        hand-encoded x86-64 guard + frozen 42-byte error
pipeline/repair/cave_finder.py  conservative zero-tail finder and overlap checks
pipeline/repair/patch_writer.py dry-run manifest writer (no candidate)
pipeline/repair/self_check.py   structural self-check (not a verdict)
```

Example on a synthetic image (never the frozen fixture):

```bash
python -m pipeline.repair.cave_finder \
  --elf var/synthetic.elf --start 0x401211 --end 0x402000 \
  --min-size 111 --patch-site 0x401194

python -m pipeline.repair.patch_writer \
  --elf var/synthetic.elf --patch-site 0x401194 --cave 0x401220 \
  --strcpy-plt 0x401060 --cave-limit 0x402000 \
  --fixture-id synthetic-01 --out var/manifest.json

python -m pipeline.repair.self_check \
  --elf var/synthetic.elf --manifest var/manifest.json
```

The manifest is currently `m5-dryrun-v0` / `EditManifestV1-draft`; it must be
replaced by M1's frozen `EditManifestV1` when that schema is published. The
`self_check` result is structural only and is not a verdict.

`cave_finder` has two modes: an explicit approved range for fixture preflight,
and an all-file-backed-R-X scan (`find_caves_in_segments`) for the product
interface. The reserved tail is a fixture convenience, not a product assumption;
absence of a cave returns `no_candidate` and must not trigger a silent segment
extension.

See `docs/repair/guard-abi.md` for the guard byte layout and ABI review note, and
`docs/repair/dryrun-tools.md` for assumptions, error codes and the preflight
command.
