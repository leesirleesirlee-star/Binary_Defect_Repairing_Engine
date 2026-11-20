"""Minimal read-only ELF64 parser and dry-run byte editor.

This module is deliberately limited to the ELF64 subset needed by the M5 repair
tools.  It uses only the Python standard library: no pyelftools, no capstone and
no lief.  The parser never writes to the file it reads; ``ELF64.preview_edits``
returns a new ``bytes`` object so callers can inspect a hypothetical candidate
without creating one on disk.

Scope and assumptions
----------------------
* ELF64, little-endian, ``ET_EXEC`` or ``ET_DYN``.
* The class parses headers, program headers, section headers, section names and
  relocation entries.  It does not interpret machine instructions.
* Out-of-range or inconsistent metadata raises ``ELFError`` instead of guessing.
* ``preview_edits`` is a dry-run primitive.  It does not validate a repair plan;
  that belongs to the caller (``patch_writer`` / ``self_check``).
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# ELF constants used by this module and by the repair tools.
ELF_HEADER_SIZE = 64
PROGRAM_HEADER_SIZE = 56
SECTION_HEADER_SIZE = 64

ELFCLASS64 = 2
ELFDATA2LSB = 1
ET_EXEC = 2
ET_DYN = 3
EM_X86_64 = 62

PT_LOAD = 1
PF_X = 0x1
PF_W = 0x2
PF_R = 0x4

SHT_REL = 9
SHT_RELA = 4
SHT_NOBITS = 8

SHF_ALLOC = 0x2
SHF_EXECINSTR = 0x4

_ELF_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
_PROGRAM_HEADER = struct.Struct("<IIQQQQQQ")
_SECTION_HEADER = struct.Struct("<IIQQQQIIQQ")
_RELA = struct.Struct("<QQq")
_REL = struct.Struct("<QQ")


class ELFError(ValueError):
    """Raised when an ELF image is malformed or outside the supported subset."""


@dataclass(frozen=True)
class Segment:
    """One program header (``PT_LOAD`` and friends)."""

    index: int
    p_type: int
    p_flags: int
    p_offset: int
    p_vaddr: int
    p_paddr: int
    p_filesz: int
    p_memsz: int
    p_align: int

    @property
    def executable(self) -> bool:
        """Return true when the segment has the executable permission bit."""
        return bool(self.p_flags & PF_X)

    @property
    def writable(self) -> bool:
        """Return true when the segment has the writable permission bit."""
        return bool(self.p_flags & PF_W)

    @property
    def readable(self) -> bool:
        """Return true when the segment has the readable permission bit."""
        return bool(self.p_flags & PF_R)

    @property
    def flags_text(self) -> str:
        """Return a compact ``R-X`` / ``RW-`` style permission string."""
        return "".join(
            letter if self.p_flags & bit else "-"
            for letter, bit in (("R", PF_R), ("W", PF_W), ("X", PF_X))
        )

    def contains_vaddr(self, vaddr: int, size: int = 1, *, file_backed: bool = True) -> bool:
        """Return true when ``[vaddr, vaddr+size)`` is inside this segment."""
        limit = self.p_filesz if file_backed else self.p_memsz
        return self.p_vaddr <= vaddr and vaddr + size <= self.p_vaddr + limit


@dataclass(frozen=True)
class Section:
    """One section header plus its resolved name (when ``.shstrtab`` exists)."""

    index: int
    name: str
    sh_name: int
    sh_type: int
    sh_flags: int
    sh_addr: int
    sh_offset: int
    sh_size: int
    sh_link: int
    sh_info: int
    sh_addralign: int
    sh_entsize: int

    @property
    def allocatable(self) -> bool:
        """Return true when the section occupies process memory."""
        return bool(self.sh_flags & SHF_ALLOC)

    @property
    def executable(self) -> bool:
        """Return true when the section has the execute permission bit."""
        return bool(self.sh_flags & SHF_EXECINSTR)

    @property
    def nobits(self) -> bool:
        """Return true for ``SHT_NOBITS`` sections (their file bytes do not exist)."""
        return self.sh_type == SHT_NOBITS


@dataclass(frozen=True)
class Relocation:
    """One relocation offset, normalized to a virtual address for ``ET_EXEC``."""

    section: str
    vaddr: int
    width: int
    reloc_type: int


@dataclass(frozen=True)
class Edit:
    """One contiguous byte replacement used by dry-run previews."""

    offset: int
    new_bytes: bytes
    old_bytes: bytes | None = None
    name: str = ""
    purpose: str = ""

    @property
    def size(self) -> int:
        """Return the number of bytes replaced by this edit."""
        return len(self.new_bytes)


class ELF64:
    """Parse an ELF64 image and expose vaddr/file-offset helpers.

    Parameters
    ----------
    data:
        Complete ELF image bytes.
    source:
        Optional display name for diagnostics; never used to write files.
    """

    def __init__(self, data: bytes, source: str | None = None) -> None:
        self.data = bytes(data)
        self.source = source or "<memory>"

        if len(self.data) < ELF_HEADER_SIZE:
            raise ELFError(f"{self.source}: image is shorter than an ELF64 header")

        (
            self.e_ident,
            self.e_type,
            self.e_machine,
            self.e_version,
            self.e_entry,
            self.e_phoff,
            self.e_shoff,
            self.e_flags,
            self.e_ehsize,
            self.e_phentsize,
            self.e_phnum,
            self.e_shentsize,
            self.e_shnum,
            self.e_shstrndx,
        ) = _ELF_HEADER.unpack_from(self.data, 0)

        self._validate_ident()
        self._validate_header_sizes()

        self.segments = tuple(self._parse_segments())
        self.sections = tuple(self._parse_sections())

    @classmethod
    def from_path(cls, path: str | Path) -> ELF64:
        """Read ``path`` into memory and parse it without modifying the file."""
        file_path = Path(path)
        return cls(file_path.read_bytes(), source=str(file_path))

    # ------------------------------------------------------------------
    # Header validation
    # ------------------------------------------------------------------
    def _validate_ident(self) -> None:
        if self.e_ident[:4] != b"\x7fELF":
            raise ELFError(f"{self.source}: missing ELF magic")
        if self.e_ident[4] != ELFCLASS64:
            raise ELFError(f"{self.source}: not ELF64 (EI_CLASS={self.e_ident[4]})")
        if self.e_ident[5] != ELFDATA2LSB:
            raise ELFError(f"{self.source}: not little-endian (EI_DATA={self.e_ident[5]})")
        if self.e_ident[6] != 1:
            raise ELFError(f"{self.source}: unsupported ELF version {self.e_ident[6]}")
        if self.e_type not in (ET_EXEC, ET_DYN):
            raise ELFError(f"{self.source}: unsupported e_type {self.e_type}")
        if self.e_machine != EM_X86_64:
            raise ELFError(f"{self.source}: unsupported e_machine {self.e_machine}")

    def _validate_header_sizes(self) -> None:
        if self.e_ehsize < ELF_HEADER_SIZE:
            raise ELFError(f"{self.source}: e_ehsize={self.e_ehsize} is too small")
        if self.e_phnum and self.e_phentsize != PROGRAM_HEADER_SIZE:
            raise ELFError(
                f"{self.source}: e_phentsize={self.e_phentsize}, expected {PROGRAM_HEADER_SIZE}"
            )
        if self.e_shnum and self.e_shentsize != SECTION_HEADER_SIZE:
            raise ELFError(
                f"{self.source}: e_shentsize={self.e_shentsize}, expected {SECTION_HEADER_SIZE}"
            )

    # ------------------------------------------------------------------
    # Program headers
    # ------------------------------------------------------------------
    def _parse_segments(self) -> list[Segment]:
        if self.e_phnum == 0:
            return []
        if self.e_phoff + self.e_phnum * self.e_phentsize > len(self.data):
            raise ELFError(f"{self.source}: program header table extends past EOF")
        segments: list[Segment] = []
        for index in range(self.e_phnum):
            offset = self.e_phoff + index * self.e_phentsize
            fields = _PROGRAM_HEADER.unpack_from(self.data, offset)
            segment = Segment(index, *fields)
            if segment.p_offset > len(self.data):
                raise ELFError(f"{self.source}: PT_LOAD #{index} offset is past EOF")
            if segment.p_offset + segment.p_filesz > len(self.data):
                raise ELFError(f"{self.source}: PT_LOAD #{index} file range is past EOF")
            if segment.p_memsz < segment.p_filesz:
                raise ELFError(f"{self.source}: PT_LOAD #{index} memsz < filesz")
            if segment.p_align > 1 and (
                segment.p_vaddr - segment.p_offset
            ) % segment.p_align != 0:
                raise ELFError(f"{self.source}: PT_LOAD #{index} vaddr/offset misaligned")
            segments.append(segment)
        return segments

    # ------------------------------------------------------------------
    # Section headers
    # ------------------------------------------------------------------
    def _parse_sections(self) -> list[Section]:
        if self.e_shnum == 0:
            return []
        end = self.e_shoff + self.e_shnum * self.e_shentsize
        if end > len(self.data):
            raise ELFError(f"{self.source}: section header table extends past EOF")
        raw: list[tuple[int, ...]] = []
        for index in range(self.e_shnum):
            offset = self.e_shoff + index * self.e_shentsize
            raw.append(_SECTION_HEADER.unpack_from(self.data, offset))
        names = self._read_shstrtab(raw)
        sections: list[Section] = []
        for index, fields in enumerate(raw):
            name = names.get(fields[0], "")
            section = Section(index, name, *fields)
            if (
                section.sh_type != SHT_NOBITS
                and section.sh_size
                and section.sh_offset + section.sh_size > len(self.data)
            ):
                raise ELFError(f"{self.source}: section {name!r} file range is past EOF")
            sections.append(section)
        return sections

    def _read_shstrtab(self, raw: list[tuple[int, ...]]) -> dict[int, str]:
        """Decode section names, returning an empty map if the table is absent."""
        if self.e_shstrndx == 0 or self.e_shstrndx >= len(raw):
            return {}
        shstr = raw[self.e_shstrndx]
        # Section header layout: name, type, flags, addr, offset, size, ...
        offset, size = shstr[4], shstr[5]
        if offset + size > len(self.data) or size == 0:
            return {}
        table = self.data[offset : offset + size]
        names: dict[int, str] = {}
        for section_name_offset in {entry[0] for entry in raw}:
            if section_name_offset >= len(table):
                continue
            end = table.find(b"\x00", section_name_offset)
            if end < 0:
                end = len(table)
            names[section_name_offset] = table[section_name_offset:end].decode(
                "utf-8", "replace"
            )
        return names

    # ------------------------------------------------------------------
    # Basic metadata
    # ------------------------------------------------------------------
    @property
    def is_executable_type(self) -> bool:
        """Return true for non-PIE executables."""
        return self.e_type == ET_EXEC

    def header_bytes(self) -> bytes:
        """Return the ELF header bytes (``e_ehsize`` bytes)."""
        return self.data[: self.e_ehsize]

    def program_header_bytes(self) -> bytes:
        """Return the complete program header table bytes."""
        if self.e_phnum == 0:
            return b""
        end = self.e_phoff + self.e_phnum * self.e_phentsize
        return self.data[self.e_phoff : end]

    def section_header_bytes(self) -> bytes:
        """Return the complete section header table bytes."""
        if self.e_shnum == 0:
            return b""
        end = self.e_shoff + self.e_shnum * self.e_shentsize
        return self.data[self.e_shoff : end]

    def headers_bytes(self) -> bytes:
        """Return ELF header + program headers + section headers as one blob."""
        return self.header_bytes() + self.program_header_bytes() + self.section_header_bytes()

    def headers_sha256(self) -> str:
        """Return the SHA-256 of :meth:`headers_bytes`."""
        return hashlib.sha256(self.headers_bytes()).hexdigest()

    def sha256(self) -> str:
        """Return the SHA-256 of the complete image."""
        return hashlib.sha256(self.data).hexdigest()

    def pt_load_segments(self) -> tuple[Segment, ...]:
        """Return only ``PT_LOAD`` segments, in program-header order."""
        return tuple(segment for segment in self.segments if segment.p_type == PT_LOAD)

    def executable_load_segments(self) -> tuple[Segment, ...]:
        """Return ``PT_LOAD`` segments that carry ``PF_X``."""
        return tuple(segment for segment in self.pt_load_segments() if segment.executable)

    # ------------------------------------------------------------------
    # Address translation
    # ------------------------------------------------------------------
    def segment_for_vaddr(
        self,
        vaddr: int,
        size: int = 1,
        *,
        file_backed: bool = True,
    ) -> Segment:
        """Return the ``PT_LOAD`` containing ``[vaddr, vaddr+size)``.

        Raises ``ELFError`` when no single load segment contains the range.
        """
        for segment in self.pt_load_segments():
            if segment.contains_vaddr(vaddr, size, file_backed=file_backed):
                return segment
        raise ELFError(
            f"{self.source}: vaddr range 0x{vaddr:x}+0x{size:x} is not in one PT_LOAD"
        )

    def vaddr_to_offset(self, vaddr: int, size: int = 1) -> int:
        """Translate a file-backed virtual address to a file offset."""
        segment = self.segment_for_vaddr(vaddr, size, file_backed=True)
        return segment.p_offset + (vaddr - segment.p_vaddr)

    def offset_to_vaddr(self, offset: int, size: int = 1) -> int:
        """Translate a file offset inside a ``PT_LOAD`` to its virtual address."""
        for segment in self.pt_load_segments():
            if segment.p_offset <= offset and offset + size <= segment.p_offset + segment.p_filesz:
                return segment.p_vaddr + (offset - segment.p_offset)
        raise ELFError(f"{self.source}: offset range 0x{offset:x}+0x{size:x} is not in a PT_LOAD")

    def read_vaddr(self, vaddr: int, size: int) -> bytes:
        """Read ``size`` file bytes starting at virtual address ``vaddr``."""
        if size < 0:
            raise ELFError("negative read size")
        offset = self.vaddr_to_offset(vaddr, size)
        end = offset + size
        if end > len(self.data):
            raise ELFError(f"{self.source}: read past EOF at 0x{offset:x}")
        return self.data[offset:end]

    def read_offset(self, offset: int, size: int) -> bytes:
        """Read ``size`` bytes at a raw file offset."""
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ELFError(f"{self.source}: offset read past EOF at 0x{offset:x}")
        return self.data[offset : offset + size]

    # ------------------------------------------------------------------
    # Sections and relocations
    # ------------------------------------------------------------------
    def section_by_name(self, name: str) -> Section | None:
        """Return the first section named ``name``, or ``None``."""
        for section in self.sections:
            if section.name == name:
                return section
        return None

    def section_bytes(self, section: Section) -> bytes:
        """Return the file bytes of a section, or empty bytes for ``SHT_NOBITS``."""
        if section.nobits:
            return b""
        if section.sh_offset + section.sh_size > len(self.data):
            raise ELFError(f"{self.source}: section {section.name!r} extends past EOF")
        return self.data[section.sh_offset : section.sh_offset + section.sh_size]

    def sections_overlapping(self, vaddr: int, size: int) -> tuple[Section, ...]:
        """Return allocated sections whose virtual range overlaps the given range."""
        result: list[Section] = []
        for section in self.sections:
            if not section.allocatable or section.sh_size == 0:
                continue
            section_end = section.sh_addr + section.sh_size
            if section.sh_addr < vaddr + size and vaddr < section_end:
                result.append(section)
        return tuple(result)

    def relocations(self) -> tuple[Relocation, ...]:
        """Parse ``SHT_REL`` / ``SHT_RELA`` entries into normalized records.

        For the supported non-PIE ``ET_EXEC`` fixture, ``r_offset`` is a virtual
        address.  The function raises ``ELFError`` on malformed tables instead of
        silently skipping them.
        """
        result: list[Relocation] = []
        for section in self.sections:
            if section.sh_type not in (SHT_REL, SHT_RELA):
                continue
            entry_size = section.sh_entsize or (
                _RELA.size if section.sh_type == SHT_RELA else _REL.size
            )
            expected = _RELA.size if section.sh_type == SHT_RELA else _REL.size
            if entry_size != expected:
                raise ELFError(
                    f"{self.source}: relocation section {section.name!r} has "
                    f"unexpected entry size {entry_size}"
                )
            if section.sh_size % entry_size != 0:
                raise ELFError(f"{self.source}: relocation section {section.name!r} is truncated")
            blob = self.section_bytes(section)
            for offset in range(0, len(blob), entry_size):
                if section.sh_type == SHT_RELA:
                    r_offset, r_info, _addend = _RELA.unpack_from(blob, offset)
                else:
                    r_offset, r_info = _REL.unpack_from(blob, offset)
                result.append(
                    Relocation(
                        section=section.name,
                        vaddr=r_offset,
                        width=8,
                        reloc_type=r_info & 0xFFFFFFFF,
                    )
                )
        return tuple(result)

    # ------------------------------------------------------------------
    # Dry-run editing
    # ------------------------------------------------------------------
    def preview_edits(
        self,
        edits: Iterable[Edit],
        *,
        verify_preimages: bool = True,
    ) -> bytes:
        """Return a new image with ``edits`` applied, without writing any file.

        The source bytes are never mutated.  Edits must be non-empty,
        non-overlapping and inside the image.  When ``old_bytes`` is supplied,
        the current bytes must match it before the replacement is accepted.
        """
        ordered = sorted(edits, key=lambda edit: edit.offset)
        if not ordered:
            return self.data

        previous_end = -1
        output = bytearray(self.data)
        for edit in ordered:
            if edit.size == 0:
                raise ELFError(f"{self.source}: empty edit {edit.name!r}")
            end = edit.offset + edit.size
            if edit.offset < 0 or end > len(output):
                raise ELFError(f"{self.source}: edit {edit.name!r} is outside the image")
            if edit.offset < previous_end:
                raise ELFError(f"{self.source}: edit {edit.name!r} overlaps a previous edit")
            if verify_preimages and edit.old_bytes is not None:
                current = bytes(output[edit.offset : end])
                if current != edit.old_bytes:
                    raise ELFError(
                        f"{self.source}: edit {edit.name!r} preimage mismatch "
                        f"at 0x{edit.offset:x}"
                    )
            output[edit.offset : end] = edit.new_bytes
            previous_end = end
        return bytes(output)


def align_up(value: int, alignment: int) -> int:
    """Return ``value`` rounded up to a multiple of ``alignment``."""
    if alignment <= 0:
        raise ValueError("alignment must be positive")
    return (value + alignment - 1) // alignment * alignment


def fits_rel32(source_next: int, target: int) -> bool:
    """Return true when a 32-bit signed displacement can reach ``target``."""
    displacement = target - source_next
    return -(2**31) <= displacement < 2**31


def encode_rel32_branch(opcode: int, source_vaddr: int, target_vaddr: int) -> bytes:
    """Encode a 5-byte ``call``/``jmp`` with a signed 32-bit displacement.

    ``opcode`` must be ``0xE8`` (call) or ``0xE9`` (jmp).  The displacement is
    measured from the instruction after the 5-byte branch.  ``ELFError`` is
    raised when the target is out of range or the opcode is unsupported.
    """
    if opcode not in (0xE8, 0xE9):
        raise ELFError(f"unsupported rel32 branch opcode 0x{opcode:02x}")
    next_vaddr = source_vaddr + 5
    if not fits_rel32(next_vaddr, target_vaddr):
        raise ELFError(
            f"rel32 branch from 0x{source_vaddr:x} cannot reach 0x{target_vaddr:x}"
        )
    return bytes([opcode]) + struct.pack("<i", target_vaddr - next_vaddr)
