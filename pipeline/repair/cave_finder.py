"""Find zero-filled, executable code caves inside an approved address range.

Inputs are an ELF64 image and an explicit reserved range (normally the
``reserved_range`` recorded by M3 after ADR 0001).  The finder is deliberately
conservative: it reports a cave only when the bytes are zero, the range is
file-backed and executable, the start is aligned, and the range does not overlap
headers, sections, relocations or a different load segment.

The finder is a dry-run tool.  It never changes the ELF and never executes it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pipeline.repair import EXIT_CHECK_FAILED, EXIT_ERROR, EXIT_OK, __version__
from pipeline.repair.elf64 import (
    ELF64,
    ELFError,
    Segment,
    align_up,
    fits_rel32,
)


class CaveFinderError(ValueError):
    """Raised when the requested range cannot be searched."""


@dataclass(frozen=True)
class CaveCandidate:
    """One candidate zero-filled region in the reserved range."""

    vaddr: int
    file_offset: int
    size: int
    fill: str
    alignment: int
    reachable_from: tuple[int, ...]
    segment_index: int = 0
    scope: str = "explicit"

    def to_dict(self) -> dict[str, object]:
        """Return the JSON-friendly representation used by the CLI/manifest."""
        return {
            "vaddr": f"0x{self.vaddr:x}",
            "file_offset": f"0x{self.file_offset:x}",
            "size": self.size,
            "fill": self.fill,
            "alignment": self.alignment,
            "reachable_from": [f"0x{site:x}" for site in self.reachable_from],
            "segment_index": self.segment_index,
            "scope": self.scope,
        }


def _overlaps(start_a: int, size_a: int, start_b: int, size_b: int) -> bool:
    """Return true when two half-open virtual ranges intersect."""
    return start_a < start_b + size_b and start_b < start_a + size_a


def _check_headers(elf: ELF64, file_offset: int, size: int) -> None:
    """Reject a candidate whose file bytes overlap an ELF header table."""
    if _overlaps(file_offset, size, 0, elf.e_ehsize):
        raise CaveFinderError("candidate overlaps the ELF header")
    if elf.e_phnum and _overlaps(
        file_offset,
        size,
        elf.e_phoff,
        elf.e_phnum * elf.e_phentsize,
    ):
        raise CaveFinderError("candidate overlaps the program header table")
    if elf.e_shnum and _overlaps(
        file_offset,
        size,
        elf.e_shoff,
        elf.e_shnum * elf.e_shentsize,
    ):
        raise CaveFinderError("candidate overlaps the section header table")


def _check_sections(elf: ELF64, vaddr: int, size: int) -> None:
    """Reject a candidate that overlaps any allocated section."""
    for section in elf.sections:
        if not section.allocatable or section.sh_size == 0:
            continue
        # NOBITS occupies memory but has no file bytes; it is still not a safe
        # cave because a later loader may write there.
        if _overlaps(vaddr, size, section.sh_addr, section.sh_size):
            raise CaveFinderError(
                f"candidate overlaps section {section.name or section.index}"
            )


def _check_relocations(elf: ELF64, vaddr: int, size: int) -> None:
    """Reject a candidate that overlaps a relocation target."""
    for relocation in elf.relocations():
        if _overlaps(vaddr, size, relocation.vaddr, relocation.width):
            raise CaveFinderError(
                f"candidate overlaps relocation in {relocation.section!r}"
            )


def _check_other_segments(
    elf: ELF64,
    containing: Segment,
    vaddr: int,
    size: int,
) -> None:
    """Reject a candidate that overlaps a different PT_LOAD."""
    for segment in elf.pt_load_segments():
        if segment.index == containing.index:
            continue
        if _overlaps(vaddr, size, segment.p_vaddr, segment.p_memsz):
            raise CaveFinderError(
                f"candidate overlaps PT_LOAD #{segment.index} ({segment.flags_text})"
            )


def find_caves(
    elf: ELF64,
    start: int,
    end: int,
    *,
    min_size: int,
    alignment: int = 16,
    patch_sites: Iterable[int] = (),
    scope: str = "explicit",
) -> list[CaveCandidate]:
    """Return zero-filled candidates in ``[start, end)``.

    Parameters
    ----------
    elf:
        Parsed ELF64 image.
    start, end:
        Approved virtual-address range.  It must be contained in one executable,
        file-backed ``PT_LOAD``.
    min_size:
        Minimum number of contiguous bytes required by the caller.
    alignment:
        Required start alignment; defaults to 16 bytes.
    patch_sites:
        Optional call-site virtual addresses.  When supplied, each candidate
        records which sites can reach it with a 32-bit displacement.

    Returns
    -------
    list[CaveCandidate]
        Sorted by virtual address.  An empty list means no safe cave was found.
    """
    if start < 0 or end <= start:
        raise CaveFinderError("range must satisfy 0 <= start < end")
    if min_size <= 0:
        raise CaveFinderError("min_size must be positive")
    if alignment <= 0:
        raise CaveFinderError("alignment must be positive")

    size = end - start
    try:
        containing = elf.segment_for_vaddr(start, size, file_backed=True)
    except ELFError as exc:
        raise CaveFinderError(str(exc)) from exc
    if not containing.executable:
        raise CaveFinderError("range is not inside an executable PT_LOAD")

    aligned_start = align_up(start, alignment)
    if aligned_start >= end:
        return []

    blob = elf.read_vaddr(aligned_start, end - aligned_start)

    sites = tuple(int(site) for site in patch_sites)
    candidates: list[CaveCandidate] = []
    for match in re.finditer(b"\x00+", blob):
        raw_start = aligned_start + match.start()
        raw_size = match.end() - match.start()
        # Trim an unaligned zero run to its first aligned start; otherwise a
        # whole-segment scan would miss a valid aligned cave inside a run that
        # begins a few bytes earlier.
        trim = (-raw_start) % alignment
        candidate_start = raw_start + trim
        candidate_size = raw_size - trim
        if candidate_size < min_size:
            continue
        if candidate_start % alignment != 0:
            continue
        try:
            file_offset = elf.vaddr_to_offset(candidate_start, candidate_size)
        except ELFError:
            continue
        try:
            _check_headers(elf, file_offset, candidate_size)
            _check_sections(elf, candidate_start, candidate_size)
            _check_relocations(elf, candidate_start, candidate_size)
            _check_other_segments(elf, containing, candidate_start, candidate_size)
        except CaveFinderError:
            # A zero run that overlaps a section, relocation or header is not a
            # cave.  Skip it and keep looking; do not abort the whole scan.
            continue

        reachable = tuple(
            site for site in sites if fits_rel32(site + 5, candidate_start)
        )
        candidates.append(
            CaveCandidate(
                vaddr=candidate_start,
                file_offset=file_offset,
                size=candidate_size,
                fill="00",
                alignment=alignment,
                reachable_from=reachable,
                segment_index=containing.index,
                scope=scope,
            )
        )
    return candidates


def find_caves_in_segments(
    elf: ELF64,
    *,
    min_size: int,
    alignment: int = 16,
    patch_sites: Iterable[int] = (),
) -> list[CaveCandidate]:
    """Scan every file-backed executable ``PT_LOAD`` for zero-filled caves.

    This is the product-facing entry point: it does not assume a fixture-specific
    reserved tail.  The fixture preflight may still call :func:`find_caves` with
    its approved range; a future product repair can call this function and, when
    it returns no candidate, surface an explicit ``no_candidate`` result rather
    than silently extending a segment.
    """
    candidates: list[CaveCandidate] = []
    for segment in elf.executable_load_segments():
        if segment.p_filesz == 0:
            continue
        start = segment.p_vaddr
        end = segment.p_vaddr + segment.p_filesz
        try:
            candidates.extend(
                find_caves(
                    elf,
                    start,
                    end,
                    min_size=min_size,
                    alignment=alignment,
                    patch_sites=patch_sites,
                    scope="executable_segments",
                )
            )
        except CaveFinderError:
            # A segment that cannot be scanned is skipped; other segments may
            # still contain a usable cave.  The caller receives [] rather than
            # a guessed candidate.
            continue
    return candidates


def largest_zero_run(elf: ELF64, start: int, end: int) -> int:
    """Return the longest contiguous zero run in an executable range.

    This is diagnostic only.  It is used when no candidate satisfies the
    requested minimum size, so the caller can report the largest available cave
    length instead of a vague "no candidate".
    """
    if start < 0 or end <= start:
        raise CaveFinderError("range must satisfy 0 <= start < end")
    try:
        segment = elf.segment_for_vaddr(start, end - start, file_backed=True)
    except ELFError as exc:
        raise CaveFinderError(str(exc)) from exc
    if not segment.executable:
        raise CaveFinderError("range is not inside an executable PT_LOAD")
    blob = elf.read_vaddr(start, end - start)
    return max((match.end() - match.start() for match in re.finditer(b"\x00+", blob)), default=0)


def build_report(
    elf_path: Path,
    start: int | None = None,
    end: int | None = None,
    min_size: int = 1,
    patch_sites: Iterable[int] = (),
) -> dict[str, object]:
    """Build a JSON-serializable cave-finder report.

    ``start``/``end`` select an approved range.  When both are omitted, every
    file-backed executable segment is scanned.  Passing only one bound is an
    input error; this prevents a caller from accidentally scanning the wrong
    half-open range.
    """
    if (start is None) != (end is None):
        return {
            "status": "error",
            "tool": "m5-cave-finder",
            "version": __version__,
            "schema_version": "m5-dryrun-v0",
            "elf": str(elf_path),
            "error": "start and end must be provided together",
        }

    range_info: dict[str, object]
    if start is None:
        range_info = {"mode": "all_executable_segments"}
    else:
        range_info = {"start": f"0x{start:x}", "end": f"0x{end:x}"}

    try:
        elf = ELF64.from_path(elf_path)
        if start is None:
            candidates = find_caves_in_segments(
                elf,
                min_size=min_size,
                patch_sites=patch_sites,
            )
        else:
            candidates = find_caves(
                elf,
                start,
                end,
                min_size=min_size,
                patch_sites=patch_sites,
            )
    except (ELFError, CaveFinderError, OSError) as exc:
        return {
            "status": "error",
            "tool": "m5-cave-finder",
            "version": __version__,
            "schema_version": "m5-dryrun-v0",
            "elf": str(elf_path),
            "range": range_info,
            "error": str(exc),
        }
    return {
        "status": "ok" if candidates else "no_candidate",
        "tool": "m5-cave-finder",
        "version": __version__,
        "schema_version": "m5-dryrun-v0",
        "elf": str(elf_path),
        "elf_sha256": elf.sha256(),
        "range": range_info,
        "min_size": min_size,
        "candidates": [candidate.to_dict() for candidate in candidates],
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; prints JSON and writes no files."""
    parser = argparse.ArgumentParser(description="Find zero-filled R-X caves (dry-run)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--start", type=lambda value: int(value, 0))
    parser.add_argument("--end", type=lambda value: int(value, 0))
    parser.add_argument("--min-size", type=int, default=1)
    parser.add_argument(
        "--patch-site",
        action="append",
        type=lambda value: int(value, 0),
        default=[],
    )
    args = parser.parse_args(argv)

    report = build_report(
        args.elf,
        args.start,
        args.end,
        args.min_size,
        patch_sites=args.patch_site,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "ok":
        return EXIT_OK
    if report["status"] == "error":
        return EXIT_ERROR
    return EXIT_CHECK_FAILED


if __name__ == "__main__":
    sys.exit(main())
