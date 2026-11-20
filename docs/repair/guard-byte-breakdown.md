# Guard byte breakdown

Status: **dry-run review material**, not an approved patch and not a verdict.
This note explains every byte emitted by `pipeline/repair/guard.py`; the example
cave is `C = 0x401220` and the original target is `strcpy@plt = 0x401060`.
The final addresses must be re-measured on the new fixture.

## 1. Redirect at the call site

```text
call site       0x401194
original        e8 c7 fe ff ff   call 0x401060
replacement     e8 87 00 00 00   call 0x401220
```

Displacement: `0x401220 - (0x401194 + 5) = 0x87` (135). The 5-byte instruction
still pushes the original return address `0x401199`, so the guard must preserve
that stack slot.

## 2. Byte table

Offsets are relative to `C`. “Next” is the offset of the following instruction.

| Offset | Bytes | Instruction | Effect | Next |
|---:|---|---|---|---:|
| 0 | `31 c0` | `xor eax, eax` | scan index = 0 | 2 |
| 2 | `80 3c 06 00` | `cmp byte ptr [rsi+rax], 0` | test source byte | 6 |
| 6 | `74 38` | `je +0x38` | NUL at 0..31 → valid | 8 |
| 8 | `ff c0` | `inc eax` | next index | 10 |
| 10 | `83 f8 20` | `cmp eax, 32` | scanned 32 bytes? | 13 |
| 13 | `72 f3` | `jb -0x0d` | no NUL yet → scan | 15 |
| 15 | `bf 02 00 00 00` | `mov edi, 2` | stderr fd | 20 |
| 20 | `48 8d 35 2a 00 00 00` | `lea rsi, [rip+0x2a]` | message pointer | 27 |
| 27 | `ba 2a 00 00 00` | `mov edx, 42` | message length | 32 |
| 32 | `b8 01 00 00 00` | `mov eax, 1` | write syscall number, reset each loop | 37 |
| 37 | `0f 05` | `syscall` | write(2, msg, 42) | 39 |
| 39 | `85 c0` | `test eax, eax` | write result | 41 |
| 41 | `7e 07` | `jle +0x07` | error/zero → exit | 43 |
| 43 | `48 01 c6` | `add rsi, rax` | advance written bytes | 46 |
| 46 | `29 c2` | `sub edx, eax` | reduce remaining count | 48 |
| 48 | `75 ee` | `jnz -0x12` | partial write → `write_loop` at 32 | 50 |
| 50 | `b8 e7 00 00 00` | `mov eax, 231` | exit_group | 55 |
| 55 | `bf 01 00 00 00` | `mov edi, 1` | status 1 | 60 |
| 60 | `0f 05` | `syscall` | exit_group(1) | 62 |
| 62 | `0f 0b` | `ud2` | never fall through | 64 |
| 64 | `e9 fb fd ff ff` | `jmp -0x205` | tail-jump to 0x401060 | 69 |
| 69 | 42 bytes | `ERROR: input exceeds destination capacity\n` | frozen message | 111 |

### 2.1 Partial-write syscall correction

A partial `write` returns the byte count in `eax`. If the loop jumped straight
back to `syscall`, `eax` would be that count instead of `1`, so the second
syscall would use the wrong number. `mov eax, 1` is therefore **inside** the
loop at offset 32; `jnz` returns to offset 32, not directly to `syscall` at 37.
This is the Issue #21 fix. The total size is unchanged (69 code + 42 data).

## 3. Branch calculations

Let `C` be the cave address; all displacements are relative to the instruction
after the branch.

| Branch | Source next | Target | Displacement (example) |
|---|---:|---:|---:|
| `je` (off 6) | `C+8` | `C+64` (valid) | `64 - 8 = 56 = 0x38` |
| `jb` (off 13) | `C+15` | `C+2` (scan) | `2 - 15 = -13 = 0xF3` |
| `lea` (off 20) | `C+27` | `C+69` (msg) | `69 - 27 = 42 = 0x2A` |
| `jle` (off 41) | `C+43` | `C+50` (exit) | `50 - 43 = 7 = 0x07` |
| `jnz` (off 48) | `C+50` | `C+32` (write loop) | `32 - 50 = -18 = 0xEE` |
| `jmp` (off 64) | `C+69` | `strcpy@plt` | `strcpy_plt - (C+69)` |

For the example `C = 0x401220`, `C + 69 = 0x401265`, so the displacement is
`0x401060 - 0x401265 = -0x205` and the bytes are `e9 fb fd ff ff`. The encoder
computes this from labels; do not hardcode it for a different cave.

The redirecting call is computed independently:
`C - (call_site + 5)`.

The redirecting call is computed independently:
`C - (call_site + 5)`.

## 4. Register and stack effects

| Register | Valid path | Reject path |
|---|---|---|
| `rax` | scan index, then `strcpy` return value | write result / syscall number |
| `rcx` | untouched | clobbered by `syscall` |
| `r11` | untouched | clobbered by `syscall` |
| `rdx` | untouched | message count |
| `rdi` | untouched (destination) | fd/status |
| `rsi` | untouched (source) | message pointer |
| `rsp` | unchanged | unchanged |
| `rbx`, `rbp`, `r12`–`r15` | untouched | untouched |

`jmp strcpy@plt` is a tail jump, not a call: the return address pushed by the
redirecting `call` is still the top of stack, so `strcpy` returns to the original
continuation. `rdi` and `rsi` are unchanged. Stack alignment is identical to the
original direct call because the guard neither pushes nor calls before the jump.

## 5. Why the length test is exactly 31/32

The scan checks source bytes at indices 0..31. A NUL at index 31 means a 31-byte
input plus terminator fits `char buf[32]`, so the guard tail-jumps to `strcpy`.
If all 32 scanned bytes are non-NUL, the terminator would land at index 32, past
the destination, so the guard rejects before calling `strcpy`. The guard does
not define the contract itself; this is the frozen `ContractV1` criterion.

## 6. Limits and verification evidence

- Code: 69 bytes; message: 42 bytes; total 111 bytes.
- Contract limits: 256 code / 64 data.
- The message must be exactly the frozen 42 ASCII bytes; a custom message is
  rejected by `build_guard`.
- `tests/repair/test_guard.py` verifies every opcode, branch displacement,
  message placement, size and tail-jump target.
- The bytes were independently disassembled during development; capstone is not
  a runtime dependency and is not imported by M5 code.
- No runtime execution is claimed on the host; M3 must execute in the guest.
