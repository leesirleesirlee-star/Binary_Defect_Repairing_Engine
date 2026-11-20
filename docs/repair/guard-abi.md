# Guard trampoline: assembly, ABI and limits (M4 review note)

Status: **dry-run proposal**. This document describes the guard bytes generated
by `pipeline/repair/guard.py`; it is not an approved repair plan and not
evidence that a candidate works.

The example addresses below come from the synthetic ELF used by the tests. The
real target uses the approved patch site, `strcpy@plt` address, cave and hash.

## 1. Placement

```text
original call site     0x401194   e8 c7 fe ff ff   call strcpy@plt (0x401060)
redirecting call       0x401194   e8 87 00 00 00   call cave       (0x401220)
cave                  0x401220   guard starts here (16-byte aligned)
```

The redirecting instruction is still a 5-byte `call`, so the CPU pushes the
original return address `0x401199`. The guard must preserve that return path.

## 2. Guard layout

Offsets are relative to the cave entry.

| Offset | Bytes | Meaning |
|---:|---|---|
| 0 | `31 c0` | `xor eax, eax` — index = 0 |
| 2 | `80 3c 06 00` | `cmp byte ptr [rsi+rax], 0` |
| 6 | `74 38` | `je valid` (offset 64) |
| 8 | `ff c0` | `inc eax` |
| 10 | `83 f8 20` | `cmp eax, 32` |
| 13 | `72 f3` | `jb scan` (offset 2) |
| 15 | `bf 02 00 00 00` | `mov edi, 2` — stderr |
| 20 | `48 8d 35 2a 00 00 00` | `lea rsi, [rip+0x2a]` — message |
| 27 | `ba 2a 00 00 00` | `mov edx, 42` |
| 32 | `b8 01 00 00 00` | `mov eax, 1` — write, reset each loop |
| 37 | `0f 05` | `syscall` — write |
| 39 | `85 c0` | `test eax, eax` |
| 41 | `7e 07` | `jle exit` (offset 50) |
| 43 | `48 01 c6` | `add rsi, rax` — partial write |
| 46 | `29 c2` | `sub edx, eax` |
| 48 | `75 ee` | `jnz write_loop` (offset 32, reset `eax`) |
| 50 | `b8 e7 00 00 00` | `mov eax, 231` — exit_group |
| 55 | `bf 01 00 00 00` | `mov edi, 1` |
| 60 | `0f 05` | `syscall` — exit_group |
| 62 | `0f 0b` | `ud2` — never fall through |
| 64 | `e9 fb fd ff ff` | `jmp strcpy@plt` (0x401060) |
| 69 | 42 bytes | `ERROR: input exceeds destination capacity\n` |

Total: **69 bytes of code + 42 bytes of data = 111 bytes**.

## 3. ABI and control flow

### Valid path (NUL at index 0..31)

At cave entry the stack contains the return address pushed by the redirecting
`call`. The guard uses only `rax` as a scan index and reads `[rsi+rax]`. It never
writes `rdi`, `rsi`, the return address, or the stack.

When a NUL is found, the guard executes `jmp strcpy@plt`. This is a tail jump:
the same return address is still on top of the stack, `rdi`/`rsi` are unchanged,
and `strcpy` returns directly to the original continuation. `strcpy`'s return
value is in `rax`, as it would be for the original call. Stack alignment is the
same as a direct call because no `push`/`call` occurs in the guard.

### Reject path (no NUL in bytes 0..31)

The guard sets up `write(2, message, 42)` and loops while `write` returns a
positive count:

- `mov eax, 1` is re-executed at the top of every iteration, so a partial-write
  return count in `eax` can never become the next syscall number;
- `add rsi, rax` advances over bytes already written;
- `sub edx, eax` reduces the remaining count;
- `jne` repeats while the count is non-zero.

If `write` returns `<= 0` (error, zero, or interrupted), the guard stops trying
and executes `exit_group(1)`. It never returns to `puts` or the original call
continuation. A failing stderr cannot produce the exact contract bytes; M3 must
reject such a candidate rather than treating it as a pass.

The `ud2` after `exit_group` prevents accidental fall-through into the valid
path if the exit syscall were ever to return.

## 4. Why the register/stack claims hold

- `rdi` and `rsi` are read-only in the valid path.
- `rax` is caller-saved and is overwritten by `strcpy` on the valid path; the
  original call would also leave `strcpy`'s return value in `rax`.
- `rdx` is untouched on the valid path; it is only used after the reject branch.
- `rcx` and `r11` are not used before the valid tail jump; the `syscall`
  instruction would clobber them only on the reject path, which never returns.
- No callee-saved register (`rbx`, `rbp`, `r12`–`r15`) is modified.
- No stack adjustment occurs before the tail jump.

## 5. Limits and invariants

- `code_size = 69 <= 256` and `message_size = 42 <= 64`.
- The guard and message fit in the ADR 0001 reserved R-X range with a large
  margin; the exact range is rechecked on the real fixture.
- Program headers, section headers, entry point and dynamic imports are not
  changed by the manifest.
- The patch site is one 5-byte `E8` call; the guard starts on a 16-byte
  boundary.
- The message is exactly the frozen ASCII string; M5 cannot substitute a
  different error.

## 6. Residual risks for M4 review

1. The guard is hand-encoded; a disassembler review of the exact bytes is
   required before G2.
2. The runtime behavior is not executed on the host; the guest must confirm the
   valid/reject paths and exact stderr.
3. The contract's NUL-termination assumption is outside the guard's control.
4. CET/shadow-stack enforcement, signals during `write`, and unusual stderr
   states need the environment assumptions in `ContractV1`.
5. The final addresses depend on the new fixture; the example offsets are not
   frozen facts.
