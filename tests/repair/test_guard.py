"""Static tests for the hand-encoded x86-64 guard.

No test executes the guard.  The assertions check the exact opcodes, branch
displacements, frozen message and the cave/PLT reachability facts.
"""

from __future__ import annotations

import struct

import pytest

from pipeline.repair.guard import (
    CODE_LIMIT,
    DATA_LIMIT,
    ERROR_MESSAGE,
    GuardError,
    build_guard,
)

CAVE = 0x401220
STRCPY_PLT = 0x401060


def test_guard_shape_and_frozen_message() -> None:
    """The guard has the expected code/data split and exact error bytes."""
    guard = build_guard(CAVE, STRCPY_PLT)
    assert guard.code_size == 69
    assert guard.message_size == 42
    assert guard.total_size == 111
    assert guard.code_size <= CODE_LIMIT
    assert guard.message_size <= DATA_LIMIT
    assert guard.message_vaddr == CAVE + 69
    assert guard.blob[69:] == ERROR_MESSAGE
    assert guard.labels == {
        "scan": 2,
        "write_loop": 32,
        "exit": 50,
        "valid": 64,
        "msg": 69,
    }


def test_guard_length_check_opcodes() -> None:
    """The length scan and its rel8 branches point at the intended labels."""
    blob = build_guard(CAVE, STRCPY_PLT).blob
    assert blob[0:2] == b"\x31\xc0"  # xor eax, eax
    assert blob[2:6] == b"\x80\x3c\x06\x00"  # cmp byte [rsi+rax], 0
    assert blob[6:8] == b"\x74\x38"  # je valid (64 - 8 = 56)
    assert blob[8:10] == b"\xff\xc0"  # inc eax
    assert blob[10:13] == b"\x83\xf8\x20"  # cmp eax, 32
    assert blob[13:15] == b"\x72\xf3"  # jb scan (2 - 15 = -13)


def test_guard_reject_path_opcodes() -> None:
    """The reject path writes the message and exits without falling through."""
    blob = build_guard(CAVE, STRCPY_PLT).blob
    assert blob[15:20] == b"\xbf\x02\x00\x00\x00"  # mov edi, 2
    assert blob[20:23] == b"\x48\x8d\x35"  # lea rsi, [rip + msg]
    assert struct.unpack_from("<i", blob, 23)[0] == 69 - 27  # 0x2a
    assert blob[27:32] == b"\xba\x2a\x00\x00\x00"  # mov edx, 42
    assert blob[32:37] == b"\xb8\x01\x00\x00\x00"  # mov eax, 1 inside loop
    assert blob[37:39] == b"\x0f\x05"  # syscall write
    assert blob[39:41] == b"\x85\xc0"  # test eax, eax
    assert blob[41:43] == b"\x7e\x07"  # jle exit (50 - 43 = 7)
    assert blob[43:46] == b"\x48\x01\xc6"  # add rsi, rax
    assert blob[46:48] == b"\x29\xc2"  # sub edx, eax
    assert blob[48:50] == b"\x75\xee"  # jnz write_loop (32 - 50 = -18)
    assert blob[50:55] == b"\xb8\xe7\x00\x00\x00"  # mov eax, 231
    assert blob[55:60] == b"\xbf\x01\x00\x00\x00"  # mov edi, 1
    assert blob[60:62] == b"\x0f\x05"  # syscall exit_group
    assert blob[62:64] == b"\x0f\x0b"  # ud2 guard against fall-through


def test_reject_path_uses_correct_syscall_numbers() -> None:
    """The reject path uses write=1 and exit_group=231, not other numbers."""
    blob = build_guard(CAVE, STRCPY_PLT).blob
    assert blob[32:37] == b"\xb8\x01\x00\x00\x00"  # mov eax, 1 (write)
    assert blob[50:55] == b"\xb8\xe7\x00\x00\x00"  # mov eax, 231 (exit_group)
    assert blob[37:39] == b"\x0f\x05"
    assert blob[60:62] == b"\x0f\x05"


def test_partial_write_loop_resets_write_number() -> None:
    """A partial write must re-enter the loop at mov eax, 1, not at syscall."""
    blob = build_guard(CAVE, STRCPY_PLT).blob
    assert blob[48] == 0x75  # jnz rel8
    displacement = struct.unpack_from("<b", blob, 49)[0]
    target = 50 + displacement
    assert target == 32  # write_loop label; mov eax, 1 is the first byte
    assert blob[target : target + 5] == b"\xb8\x01\x00\x00\x00"
    assert blob[37:39] == b"\x0f\x05"
    assert blob[50:55] == b"\xb8\xe7\x00\x00\x00"


def test_guard_valid_path_jumps_to_strcpy_plt() -> None:
    """The valid path tail-jumps to the original PLT target."""
    guard = build_guard(CAVE, STRCPY_PLT)
    assert guard.blob[64:65] == b"\xe9"
    displacement = struct.unpack_from("<i", guard.blob, 65)[0]
    assert displacement == STRCPY_PLT - (CAVE + 69)
    assert guard.jmp_plt_offset == 64
    assert guard.jmp_plt_rel32 == displacement


def test_guard_rejects_custom_message() -> None:
    """M5 cannot silently invent a different stderr message."""
    with pytest.raises(GuardError, match="frozen contract"):
        build_guard(CAVE, STRCPY_PLT, b"different\n")


def test_guard_rejects_out_of_range_plt() -> None:
    """A PLT target outside rel32 is rejected instead of truncated."""
    with pytest.raises(GuardError, match="rel32"):
        build_guard(CAVE, CAVE + 2**31 + 69)


def test_guard_is_deterministic() -> None:
    """The same cave/target produces byte-identical output."""
    assert build_guard(CAVE, STRCPY_PLT).blob == build_guard(CAVE, STRCPY_PLT).blob
