"""Minimal read-only ELF64 parser for the deterministic verifier.

The verifier parses bytes only: it never executes an ELF, never writes one and
never imports ``pipeline.repair``.  Decoding is limited to the facts V0/V1 need
(ELF header, program headers, section headers, section names, dynamic imports
and relocation targets), with explicit bounds checks so a malformed candidate is
a verification finding, not a crash in the verifier.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
ELFDATA2LSB = 1
EV_CURRENT = 1
ET_EXEC = 2
EM_X86_64 = 62

PT_LOAD = 1
PF_X = 1
PF_W = 2
PF_R = 4

SHT_NOBITS = 8
SHT_RELA = 4
SHT_REL = 9
DT_NEEDED = 1

ELF_HEADER_SIZE = 64
E_ENTRY_OFFSET = 24

_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
_PHDR = struct.Struct("<IIQQQQQQ")
_SHDR = struct.Struct("<IIQQQQIIQQ")


class ELFError(ValueError):
    """Raised when bytes do not describe a well-formed ELF64 image."""


@dataclass(frozen=True)
class ProgramHeader:
    """One decoded ELF64 program header."""

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
        """Return true when the segment is mapped executable."""
        return bool(self.p_flags & PF_X)

    @property
    def writable(self) -> bool:
        """Return true when the segment is mapped writable."""
        return bool(self.p_flags & PF_W)


@dataclass(frozen=True)
class Section:
    """One decoded ELF64 section header; ``name`` is resolved via shstrtab."""

    index: int
    name: str
    sh_type: int
    sh_flags: int
    sh_addr: int
    sh_offset: int
    sh_size: int
    sh_entsize: int


@dataclass(frozen=True)
class ELF64:
    """An immutable in-memory ELF64 image decoded from raw bytes."""

    data: bytes
    source: str
    e_type: int
    e_machine: int
    e_entry: int
    e_flags: int
    e_phoff: int
    e_phentsize: int
    e_phnum: int
    e_shoff: int
    e_shentsize: int
    e_shnum: int
    e_shstrndx: int
    program_headers: tuple[ProgramHeader, ...]
    sections: tuple[Section, ...]

    # --- construction -------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes, *, source: str = "<bytes>") -> ELF64:
        """Decode ``data`` or raise :class:`ELFError` with a precise reason."""
        if len(data) < ELF_HEADER_SIZE:
            raise ELFError(f"{source}: shorter than an ELF64 header")
        if data[:4] != ELF_MAGIC:
            raise ELFError(f"{source}: not an ELF file")
        if data[4] != ELFCLASS64:
            raise ELFError(f"{source}: not ELF64")
        if data[5] != ELFDATA2LSB:
            raise ELFError(f"{source}: not little-endian")
        if data[6] != EV_CURRENT:
            raise ELFError(f"{source}: unsupported ELF version {data[6]}")
        header = _HEADER.unpack_from(data, 0)
        (_, e_type, e_machine, e_version, e_entry, e_phoff, e_shoff, e_flags,
         e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = header
        if e_version != EV_CURRENT:
            raise ELFError(f"{source}: unsupported header version {e_version}")
        if e_ehsize != ELF_HEADER_SIZE:
            raise ELFError(f"{source}: unexpected ELF header size {e_ehsize}")
        if e_phnum and (e_phentsize != _PHDR.size or e_phoff == 0):
            raise ELFError(f"{source}: unsupported program header table layout")
        if e_phnum and e_phoff + e_phnum * e_phentsize > len(data):
            raise ELFError(f"{source}: program header table out of bounds")
        if e_shnum == 0:
            if e_shoff or e_shstrndx:
                raise ELFError(f"{source}: inconsistent empty section table")
        else:
            if e_shentsize != _SHDR.size or e_shoff == 0:
                raise ELFError(f"{source}: unsupported section header table layout")
            if e_shoff + e_shnum * e_shentsize > len(data):
                raise ELFError(f"{source}: section header table out of bounds")
            if e_shstrndx >= e_shnum:
                raise ELFError(f"{source}: section name string table index out of range")
        program_headers = tuple(
            ProgramHeader(index, *_PHDR.unpack_from(data, e_phoff + index * e_phentsize))
            for index in range(e_phnum)
        )
        raw_sections = [
            _SHDR.unpack_from(data, e_shoff + index * e_shentsize)
            for index in range(e_shnum)
        ]
        shstr = b""
        if e_shnum:
            _, sh_type, _, _, sh_offset, sh_size, _, _, _, _ = raw_sections[e_shstrndx]
            if sh_type != 3:
                raise ELFError(f"{source}: section name table is not a string table")
            if sh_offset + sh_size > len(data):
                raise ELFError(f"{source}: section name table out of bounds")
            shstr = data[sh_offset:sh_offset + sh_size]
        sections = []
        for index, raw in enumerate(raw_sections):
            sh_name, sh_type, sh_flags, sh_addr, sh_offset, sh_size, _, _, _, sh_entsize = raw
            if sh_type != SHT_NOBITS and sh_offset + sh_size > len(data):
                raise ELFError(f"{source}: section {index} out of bounds")
            sections.append(Section(index, _cstring(shstr, sh_name), sh_type, sh_flags,
                                    sh_addr, sh_offset, sh_size, sh_entsize))
        for segment in program_headers:
            if segment.p_filesz and segment.p_offset + segment.p_filesz > len(data):
                raise ELFError(f"{source}: segment {segment.index} out of bounds")
        return cls(data, source, e_type, e_machine, e_entry, e_flags, e_phoff,
                   e_phentsize, e_phnum, e_shoff, e_shentsize, e_shnum, e_shstrndx,
                   program_headers, tuple(sections))

    # --- raw views ----------------------------------------------------
    def sha256(self) -> str:
        """Return the lowercase SHA-256 hex digest of the image bytes."""
        return hashlib.sha256(self.data).hexdigest()

    def header_without_entry(self) -> bytes:
        """Return the ELF header with ``e_entry`` zeroed for identity comparison."""
        header = bytearray(self.data[:ELF_HEADER_SIZE])
        header[E_ENTRY_OFFSET:E_ENTRY_OFFSET + 8] = bytes(8)
        return bytes(header)

    def program_header_bytes(self) -> bytes:
        """Return the raw program header table bytes."""
        return self.data[self.e_phoff:self.e_phoff + self.e_phnum * self.e_phentsize]

    def section_header_bytes(self) -> bytes:
        """Return the raw section header table bytes."""
        return self.data[self.e_shoff:self.e_shoff + self.e_shnum * self.e_shentsize]

    # --- segments -----------------------------------------------------
    def load_segments(self) -> tuple[ProgramHeader, ...]:
        """Return every PT_LOAD program header in table order."""
        return tuple(segment for segment in self.program_headers if segment.p_type == PT_LOAD)

    def executable_segments(self) -> tuple[ProgramHeader, ...]:
        """Return every executable PT_LOAD program header."""
        return tuple(segment for segment in self.load_segments() if segment.executable)

    def segment_for_vaddr(self, vaddr: int, size: int) -> ProgramHeader | None:
        """Return the first PT_LOAD that maps ``[vaddr, vaddr+size)``, or None."""
        for segment in self.load_segments():
            if segment.p_vaddr <= vaddr and vaddr + size <= segment.p_vaddr + segment.p_memsz:
                return segment
        return None

    def segment_for_file_range(self, offset: int, size: int) -> ProgramHeader | None:
        """Return the first PT_LOAD whose file range contains ``[offset, offset+size)``."""
        for segment in self.load_segments():
            if (segment.p_offset <= offset
                    and offset + size <= segment.p_offset + segment.p_filesz):
                return segment
        return None

    def vaddr_in_executable(self, vaddr: int) -> bool:
        """Return true when ``vaddr`` is mapped by an executable PT_LOAD."""
        return any(
            segment.p_vaddr <= vaddr < segment.p_vaddr + segment.p_memsz
            for segment in self.executable_segments()
        )

    def vaddr_to_offset(self, vaddr: int, size: int) -> int:
        """Translate a virtual range to its file offset, or raise ELFError."""
        segment = self.segment_for_vaddr(vaddr, size)
        if segment is None:
            raise ELFError(f"vaddr 0x{vaddr:x} is not mapped by a PT_LOAD")
        offset = segment.p_offset + (vaddr - segment.p_vaddr)
        if offset + size > segment.p_offset + segment.p_filesz:
            raise ELFError(f"vaddr 0x{vaddr:x} is not file-backed")
        return offset

    def read_vaddr(self, vaddr: int, size: int) -> bytes:
        """Return the file bytes mapped at ``vaddr``."""
        offset = self.vaddr_to_offset(vaddr, size)
        return self.data[offset:offset + size]

    # --- sections -----------------------------------------------------
    def section_by_name(self, name: str) -> Section | None:
        """Return the first section named ``name``, or None."""
        for section in self.sections:
            if section.name == name:
                return section
        return None

    def section_bytes(self, section: Section | None) -> bytes | None:
        """Return raw section bytes (empty for SHT_NOBITS), or None if absent."""
        if section is None:
            return None
        if section.sh_type == SHT_NOBITS:
            return b""
        return self.data[section.sh_offset:section.sh_offset + section.sh_size]

    def dynamic_needed(self) -> tuple[str, ...]:
        """Return the DT_NEEDED strings from ``.dynamic`` in table order."""
        dynamic = self.section_bytes(self.section_by_name(".dynamic"))
        strtab = self.section_bytes(self.section_by_name(".dynstr"))
        if not dynamic or strtab is None:
            return ()
        needed = []
        for offset in range(0, len(dynamic) - 15, 16):
            tag, value = struct.unpack_from("<qQ", dynamic, offset)
            if tag == 0:
                break
            if tag == DT_NEEDED:
                needed.append(_cstring(strtab, value))
        return tuple(needed)

    def relocation_offsets(self) -> tuple[tuple[str, int], ...]:
        """Return ``(section_name, r_offset)`` for every REL/RELA entry."""
        entries: list[tuple[str, int]] = []
        for section in self.sections:
            if section.sh_type not in (SHT_REL, SHT_RELA):
                continue
            raw = self.section_bytes(section) or b""
            entry_size = section.sh_entsize or (24 if section.sh_type == SHT_RELA else 16)
            if entry_size < 16:
                continue
            for offset in range(0, len(raw) - entry_size + 1, entry_size):
                entries.append((section.name, struct.unpack_from("<Q", raw, offset)[0]))
        return tuple(entries)


def _cstring(blob: bytes, offset: int) -> str:
    """Return the NUL-terminated ASCII string at ``offset`` (or '')."""
    if offset < 0 or offset >= len(blob):
        return ""
    end = blob.find(b"\0", offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode("utf-8", errors="replace")
