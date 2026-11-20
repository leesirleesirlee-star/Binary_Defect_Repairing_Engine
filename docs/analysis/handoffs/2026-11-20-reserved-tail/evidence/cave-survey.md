# Executable-space survey

Date: 2026-11-20

Sample: `fixtures/stack-overflow-01/vuln.elf` from commit
`20e102bbb28bc057784f0650429ae1d60572ed87`.
SHA-256: `10602531c92092cffbdc34688e12e4b97548cc2c03f4453506bdd4f1c9058d07`.

This is a static survey, not a repair, a proof that any range is unused, or a
gate result. The sample was not executed or modified.

## Method

In the guest, the sample copy was read-only. Each analysis command ran as
UID 1003 with `no_new_privs`, in a temporary network namespace and with a
15-second timeout. The commands were `objdump -drw -M intel --insn-width=16`,
`readelf -r -s -W -wf`, `od -Ax -tx1 -v -j 4096 -N 529`, and
`readelf -dW -x .init_array -x .fini_array`, each applied to the sample.
Each returned exit code 0. This was not the broker's jobwrap executor.

## Results

The executable `PT_LOAD` spans virtual addresses `0x401000` through
`0x401210` inclusive. Its file offset starts at `0x1000`, and its file and
memory sizes are both `0x211`. The `.fini` section ends at the same address as
the segment, so there is no trailing region within this segment.

The following ranges contain apparent padding and are candidates for further
review, not approved edit locations. Ranges are inclusive.

| Virtual addresses | File offsets | Bytes | Observation |
| --- | --- | ---: | --- |
| `0x40101b-0x40101f` | `0x101b-0x101f` | 5 | Zero bytes between `.init` and `.plt` |
| `0x4010b6-0x4010bf` | `0x10b6-0x10bf` | 10 | Alignment NOP after `_start`'s `hlt` |
| `0x4010c5-0x4010cf` | `0x10c5-0x10cf` | 11 | Alignment NOPs after a return |
| `0x4010f1-0x4010ff` | `0x10f1-0x10ff` | 15 | Alignment NOPs after a return |
| `0x401131-0x40113f` | `0x1131-0x113f` | 15 | Alignment NOPs after a return |
| `0x401161-0x40116f` | `0x1161-0x116f` | 15 | Alignment NOPs after a return |
| `0x401202-0x401203` | `0x1202-0x1203` | 2 | Zero bytes between `.text` and `.fini` |

The inspected disassembly shows no direct branch to those ranges. The listed
dynamic relocation write locations are outside the executable segment. The
dynamic init/fini addresses and the contents of `.init_array` and
`.fini_array` point outside the listed ranges. These checks do not rule out
indirect control flow, unrecognized references, or other semantic effects.
Some one-byte and PLT NOPs were deliberately not included: a NOP is not by
itself evidence of dead code, and some padding is on a fall-through path.

The largest listed contiguous range is 15 bytes. The contract's required error
message alone is 42 ASCII bytes including its newline. Fragmenting a payload
or reusing data elsewhere has not been designed or validated, and the current
contract specifies a verified-unused tail of the existing executable segment.
No proposed edit is authorized by this survey.

Supporting outputs (line endings and trailing whitespace normalized; FILE symbols redacted in `cave-readelf.txt`): `cave-objdump.txt`, `cave-readelf.txt`, `cave-hex.txt`,
`cave-init.txt`, `segments.txt`, and `sections.txt` in the same directory.
The symbol output can contain build-related names and must be filtered before
being included in any model input.
