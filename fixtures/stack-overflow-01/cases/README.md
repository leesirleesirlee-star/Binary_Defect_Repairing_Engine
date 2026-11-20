# Case corpus

`cases/valid/` contains inputs that must return normally:

```text
empty.bin   0 bytes
short.bin   6 bytes: "hello\n"
max32.bin   32 bytes: the maximum accepted by the 32-byte buffer contract
```

`cases/invalid/` contains inputs that must trigger the defect:

```text
return-overwrite-40.bin  40 bytes: 32 buffer + saved EBP + return address
```

`cases/poc.bin` is the canonical 64-byte PoC:

```text
offset 0..31   'A' * 32
offset 32..35  'B' * 4          saved EBP
offset 36..39  ef be ad de      return address (0xdeadbeef)
offset 40..63  'C' * 24
```

The exact oracle is in `../contract.json`; do not edit this corpus after the
fixture is frozen.
