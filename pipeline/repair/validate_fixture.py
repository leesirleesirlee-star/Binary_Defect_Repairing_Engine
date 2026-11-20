"""One-shot dry-run validation for a new fixture handoff.

The script is intentionally a framework: it runs only after M1/M3 publish the
fixture with ADR 0001's reserved R-X tail.  It never writes a candidate, never
modifies the fixture and never writes a verdict.  If the fixture does not match
the expected structural facts it returns ``unsupported`` instead of adapting.

Stages
------
1. parse the ELF64 and record its hash;
2. find a zero-filled, aligned, reachable cave in the approved range;
3. build an in-memory edit manifest;
4. optionally write the manifest JSON;
5. run the structural self-check;
6. write a JSON report to ``--out``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.repair import EXIT_CHECK_FAILED, EXIT_ERROR, EXIT_OK, __version__
from pipeline.repair.cave_finder import CaveFinderError, find_caves, largest_zero_run
from pipeline.repair.elf64 import ELF64, ELFError, fits_rel32
from pipeline.repair.patch_writer import (
    PatchWriterError,
    build_manifest,
    write_manifest,
)
from pipeline.repair.self_check import check_manifest


class FixtureValidationError(ValueError):
    """Raised when the input cannot be validated at all."""


def _stage(name: str, status: str, detail: str = "") -> dict[str, str]:
    """Build one report stage record."""
    return {"name": name, "status": status, "detail": detail}


def validate_fixture(
    elf_path: str | Path,
    *,
    start: int,
    end: int,
    patch_site: int,
    strcpy_plt: int,
    min_size: int = 111,
    manifest_out: str | Path | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Run the dry-run validation pipeline and return a report.

    The report is a structural preflight, not a verdict.  A successful result
    means only that the fixture has the shape M5's dry-run tools expect.
    """
    path = Path(elf_path)
    report: dict[str, Any] = {
        "tool": "m5-validate-fixture",
        "version": __version__,
        "schema_version": "m5-dryrun-v0",
        "status": "error",
        "dry_run": True,
        "candidate_written": False,
        "verdict_written_by_m5": False,
        "fixture": str(path),
        "range": {"start": f"0x{start:x}", "end": f"0x{end:x}"},
        "patch_site": f"0x{patch_site:x}",
        "strcpy_plt": f"0x{strcpy_plt:x}",
        "stages": [],
    }

    try:
        elf = ELF64.from_path(path)
    except (OSError, ELFError) as exc:
        report["stages"].append(_stage("parse_elf", "error", str(exc)))
        return report
    report["original_sha256"] = elf.sha256()
    report["stages"].append(_stage("parse_elf", "ok", f"sha256={elf.sha256()}"))

    # Check the patch site's preimage before scanning for caves.  A wrong call
    # site is a fixture/plan mismatch (error), not a missing-cave condition.
    try:
        patch_segment = elf.segment_for_vaddr(patch_site, 5, file_backed=True)
        patch_bytes = elf.read_vaddr(patch_site, 5)
    except ELFError as exc:
        report["status"] = "unsupported"
        report["stages"].append(_stage("patch_site_preimage", "unsupported", str(exc)))
        return report
    if not patch_segment.executable:
        report["status"] = "unsupported"
        report["stages"].append(
            _stage("patch_site_preimage", "unsupported", "patch site is not executable")
        )
        return report
    if patch_bytes[0] != 0xE8:
        report["status"] = "error"
        report["stages"].append(
            _stage(
                "patch_site_preimage",
                "error",
                f"expected E8..., measured {patch_bytes.hex()}",
            )
        )
        report["patch_site_original_bytes"] = patch_bytes.hex()
        return report
    report["patch_site_original_bytes"] = patch_bytes.hex()
    report["stages"].append(
        _stage("patch_site_preimage", "ok", f"measured {patch_bytes.hex()}")
    )

    try:
        candidates = find_caves(
            elf,
            start,
            end,
            min_size=min_size,
            patch_sites=(patch_site,),
        )
    except CaveFinderError as exc:
        report["status"] = "unsupported"
        report["stages"].append(_stage("cave_finder", "unsupported", str(exc)))
        return report
    if not candidates:
        try:
            max_run = largest_zero_run(elf, start, end)
        except CaveFinderError:
            max_run = 0
        report["status"] = "no_candidate"
        report["max_zero_run"] = max_run
        report["stages"].append(
            _stage(
                "cave_finder",
                "no_candidate",
                f"no zero-filled aligned cave >= {min_size}; max zero run={max_run}",
            )
        )
        return report
    cave = candidates[0]
    report["cave"] = cave.to_dict()
    report["stages"].append(
        _stage("cave_finder", "ok", f"cave=0x{cave.vaddr:x} size={cave.size}")
    )

    if not fits_rel32(patch_site + 5, cave.vaddr):
        report["status"] = "unsupported"
        report["stages"].append(
            _stage(
                "rel32_reachability",
                "unsupported",
                f"offset {cave.vaddr - (patch_site + 5)} exceeds signed 32-bit range",
            )
        )
        return report
    report["stages"].append(
        _stage(
            "rel32_reachability",
            "ok",
            f"offset {cave.vaddr - (patch_site + 5)}",
        )
    )

    try:
        manifest = build_manifest(
            path,
            patch_site_vaddr=patch_site,
            cave_vaddr=cave.vaddr,
            strcpy_plt_vaddr=strcpy_plt,
            cave_limit_vaddr=end,
            created_at=created_at,
        )
    except PatchWriterError as exc:
        message = str(exc)
        lowered = message.lower()
        if "patch-site bytes differ" in lowered or "does not start with e8" in lowered:
            status = "error"
        elif "rel32" in lowered:
            status = "unsupported"
        elif "does not fit" in lowered or "beyond approved limit" in lowered:
            status = "no_candidate"
        else:
            status = "unsupported"
        report["status"] = status
        report["stages"].append(_stage("patch_manifest", status, message))
        return report
    report["stages"].append(
        _stage("patch_manifest", "ok", f"manifest_sha256={manifest['manifest_sha256']}")
    )
    report["manifest_sha256"] = manifest["manifest_sha256"]
    report["manifest_dry_run"] = manifest["dry_run"]
    report["candidate_written"] = manifest["preview"]["candidate_written"]

    if manifest_out is not None:
        try:
            written = write_manifest(manifest, manifest_out)
        except (OSError, PatchWriterError) as exc:
            report["status"] = "error"
            report["stages"].append(_stage("write_manifest", "error", str(exc)))
            return report
        report["manifest_path"] = str(written)
        report["stages"].append(_stage("write_manifest", "ok", str(written)))

    self_check = check_manifest(path, manifest)
    report["self_check"] = self_check
    if self_check.get("status") != "checks_passed":
        report["status"] = "dry_run_checks_failed"
        report["stages"].append(
            _stage("self_check", "failed", "; ".join(self_check.get("failures", [])))
        )
        return report
    report["stages"].append(_stage("self_check", "ok", "structural checks passed"))
    report["status"] = "dry_run_checks_passed"
    report["note"] = (
        "Structural dry-run only; not a verdict, not a candidate, and not evidence "
        "of correctness. M3 owns verification."
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; writes a JSON report and, optionally, a manifest JSON."""
    parser = argparse.ArgumentParser(description="M5 dry-run fixture preflight")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--start", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--end", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--patch-site", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--strcpy-plt", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--min-size", type=int, default=111)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    report = validate_fixture(
        args.elf,
        start=args.start,
        end=args.end,
        patch_site=args.patch_site,
        strcpy_plt=args.strcpy_plt,
        min_size=args.min_size,
        manifest_out=args.manifest_out,
        created_at=args.created_at,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "dry_run_checks_passed":
        return EXIT_OK
    if report["status"] == "error":
        return EXIT_ERROR
    return EXIT_CHECK_FAILED


if __name__ == "__main__":
    sys.exit(main())
