"""Build the x86-64 guard trampoline for the stack-overflow fixture.

The guard is *data for a dry-run manifest*: this module never writes a binary and
never executes the generated code.  M5 must not run model-generated code on the
host; execution belongs to M3's disposable guest.

Control flow
------------
The original ``call strcpy@plt`` is redirected to this guard with a 5-byte
``call``.  The call pushes the original return address, so the guard can:

1. scan the source string for a NUL in bytes 0..31;
2. on a NUL, tail-jump to the original ``strcpy@plt`` with ``rdi``/``rsi`` and
   the return address untouched;
3. when no NUL is present in those 32 bytes, write the frozen 42-byte error
   message to ``stderr`` and terminate with ``exit_group(1)``.

The reject path uses raw Linux syscalls so it adds no dynamic import or PLT
entry.  A write loop handles partial writes.  A failing or closed ``stderr``
cannot produce the contract's exact bytes; the guard exits 1 in that case and
M3's verifier is expected to reject the candidate rather than treating it as a
success.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Frozen by ContractV1 / cases.json.  Do not change this string in M5 code.
ERROR_MESSAGE = b"ERROR: input exceeds destination capacity\n"
ERROR_MESSAGE_SIZE = len(ERROR_MESSAGE)
CODE_LIMIT = 256
DATA_LIMIT = 64


class GuardError(ValueError):
    """Raised when the guard cannot be encoded within the approved limits."""


@dataclass(frozen=True)
class GuardProgram:
    """Encoded guard and the metadata needed by the edit manifest."""

    blob: bytes
    message: bytes
    cave_vaddr: int
    message_offset: int
    message_vaddr: int
    code_size: int
    message_size: int
    jmp_plt_offset: int
    jmp_plt_rel32: int
    labels: dict[str, int]

    @property
    def total_size(self) -> int:
        """Return the full number of bytes written into the reserved cave."""
        return len(self.blob)


class _Assembler:
    """Tiny label/fixup assembler for the fixed guard sequence.

    It intentionally supports only the encodings used below.  This keeps the
    implementation auditable and avoids an opaque instruction encoder.
    """

    def __init__(self) -> None:
        self.buf = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str, int]] = []

    def emit(self, raw: bytes) -> None:
        """Append already-encoded bytes."""
        self.buf.extend(raw)

    def label(self, name: str) -> None:
        """Bind ``name`` to the current offset."""
        if name in self.labels:
            raise GuardError(f"duplicate label {name!r}")
        self.labels[name] = len(self.buf)

    def rel8(self, target: str) -> None:
        """Emit one signed 8-bit displacement byte for ``target``."""
        displacement_at = len(self.buf)
        self.buf.append(0)
        self.fixups.append((displacement_at, target, "rel8", displacement_at + 1))

    def rel32(self, target: str) -> None:
        """Emit one signed 32-bit displacement for ``target``."""
        displacement_at = len(self.buf)
        self.buf.extend(b"\x00\x00\x00\x00")
        self.fixups.append((displacement_at, target, "rel32", displacement_at + 4))

    def resolve(self, base_vaddr: int, external: dict[str, int]) -> None:
        """Resolve fixups relative to the cave's virtual address."""
        targets = {name: base_vaddr + offset for name, offset in self.labels.items()}
        targets.update(external)
        for displacement_at, target, kind, next_offset in self.fixups:
            if target not in targets:
                raise GuardError(f"undefined label {target!r}")
            delta = targets[target] - (base_vaddr + next_offset)
            if kind == "rel8":
                if not -128 <= delta <= 127:
                    raise GuardError(f"rel8 to {target!r} out of range: {delta}")
                self.buf[displacement_at] = struct.pack("<b", delta)[0]
            else:
                if not -(2**31) <= delta < 2**31:
                    raise GuardError(f"rel32 to {target!r} out of range: {delta}")
                self.buf[displacement_at : displacement_at + 4] = struct.pack("<i", delta)


def build_guard(
    cave_vaddr: int,
    strcpy_plt_vaddr: int,
    message: bytes = ERROR_MESSAGE,
) -> GuardProgram:
    """Encode the guard for a cave at ``cave_vaddr``.

    Parameters
    ----------
    cave_vaddr:
        Virtual address where the first guard byte will be written.
    strcpy_plt_vaddr:
        Virtual address of the original ``strcpy@plt`` target.
    message:
        Must be the frozen 42-byte contract message.  A custom message is
        rejected so the code cannot silently drift from the contract.
    """
    if message != ERROR_MESSAGE:
        raise GuardError("guard message must match the frozen contract exactly")
    if cave_vaddr < 0 or strcpy_plt_vaddr < 0:
        raise GuardError("virtual addresses must be non-negative")

    asm = _Assembler()

    # eax = 0: source index for the length scan.
    asm.emit(b"\x31\xc0")
    asm.label("scan")

    # cmp byte ptr [rsi + rax], 0
    asm.emit(b"\x80\x3c\x06\x00")

    # je valid: a NUL in bytes 0..31 means the terminator fits in buf[32].
    asm.emit(b"\x74")
    asm.rel8("valid")

    # inc eax
    asm.emit(b"\xff\xc0")

    # cmp eax, 32
    asm.emit(b"\x83\xf8\x20")

    # jb scan: after 32 non-NUL bytes the guard falls through to reject.
    asm.emit(b"\x72")
    asm.rel8("scan")

    # Reject path: write(2, message, 42) with a partial-write loop.
    asm.emit(b"\xb8\x01\x00\x00\x00")  # mov eax, 1 (write)
    asm.emit(b"\xbf\x02\x00\x00\x00")  # mov edi, 2 (stderr)
    asm.emit(b"\x48\x8d\x35")  # lea rsi, [rip + message]
    asm.rel32("msg")
    asm.emit(b"\xba\x2a\x00\x00\x00")  # mov edx, 42

    asm.label("write_loop")
    asm.emit(b"\x0f\x05")  # syscall
    asm.emit(b"\x85\xc0")  # test eax, eax
    asm.emit(b"\x7e")  # jle exit
    asm.rel8("exit")
    asm.emit(b"\x48\x01\xc6")  # add rsi, rax
    asm.emit(b"\x29\xc2")  # sub edx, eax
    asm.emit(b"\x75")  # jnz write_loop
    asm.rel8("write_loop")

    asm.label("exit")
    asm.emit(b"\xb8\xe7\x00\x00\x00")  # mov eax, 231 (exit_group)
    asm.emit(b"\xbf\x01\x00\x00\x00")  # mov edi, 1
    asm.emit(b"\x0f\x05")  # syscall
    asm.emit(b"\x0f\x0b")  # ud2: never fall through to the valid path

    # Valid path: tail-jump to the original strcpy@plt.  rdi/rsi and the
    # return address pushed by the redirecting call are untouched.
    asm.label("valid")
    asm.emit(b"\xe9")  # jmp rel32
    asm.rel32("strcpy_plt")

    asm.label("msg")
    asm.emit(message)

    asm.resolve(cave_vaddr, {"strcpy_plt": strcpy_plt_vaddr})

    labels = dict(asm.labels)
    message_offset = labels["msg"]
    message_vaddr = cave_vaddr + message_offset
    code_size = message_offset
    # The jmp instruction sits at labels["valid"]; its displacement is relative
    # to the following instruction (offset + 5).
    jmp_next = labels["valid"] + 5
    jmp_rel32 = strcpy_plt_vaddr - (cave_vaddr + jmp_next)

    if code_size > CODE_LIMIT:
        raise GuardError(f"guard code {code_size} bytes exceeds {CODE_LIMIT}")
    if len(message) > DATA_LIMIT:
        raise GuardError(f"guard data {len(message)} bytes exceeds {DATA_LIMIT}")

    return GuardProgram(
        blob=bytes(asm.buf),
        message=message,
        cave_vaddr=cave_vaddr,
        message_offset=message_offset,
        message_vaddr=message_vaddr,
        code_size=code_size,
        message_size=len(message),
        jmp_plt_offset=labels["valid"],
        jmp_plt_rel32=jmp_rel32,
        labels=labels,
    )
