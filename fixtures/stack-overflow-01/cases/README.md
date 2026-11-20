# Case corpus

The frozen corpus is `cases/cases.json`; `poc.txt` is the 64-byte PoC.

```text
valid-0      ""             stdout "\n"
valid-1      "A"            stdout "A\n"
valid-5      "hello"        stdout "hello\n"
valid-31     31 x "A"       stdout 31 x "A" + "\n"
valid-punct  "a-b_c.9"      stdout "a-b_c.9\n"

invalid-32   32 x "A"       original: crash or undefined; candidate: exit 1, stderr, no stdout
invalid-33   33 x "A"       original: crash or undefined; candidate: exit 1, stderr, no stdout
invalid-64   64 x "A"       original: SIGSEGV; candidate: exit 1, stderr, no stdout
invalid-128  128 x "A"      original: SIGSEGV; candidate: exit 1, stderr, no stdout
```

Inputs are passed as `argv[1]`, never through a shell. Candidate invalid
behaviour is exactly:

```text
ERROR: input exceeds destination capacity\n
exit 1
no stdout
no signal
```

The original's `invalid-32`/`invalid-33` result is recorded, not asserted as a
crash: it may silently corrupt the saved frame.
