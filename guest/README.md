# Guest

Owned by M3 (`guest` module). **The only place a fixture, candidate or
model-generated code may execute.**

## Isolation

- Disposable Linux x86-64 VM or container snapshot.
- No network, no credentials, no provider key, no host home directory.
- Original binary read-only; reset the snapshot between the original and the
  candidate run.
- Timeout per case (default 5 s); capture stdout, stderr, exit code and signal.
- Record the guest image, kernel, libc and tool versions in the observation.

## Runner

`run_cases.py`:

```text
input:  binary path, case set path, output path
output: ObservationV1 JSON, one row per case
exit:   0 if every case was collected; the verdict is computed elsewhere
```

- Use `execve` with an argv array; never a shell string.
- Bytes are base64 in the observation so the evidence is exact.
- A timeout is `timed_out: true`, never a pass.
- A signal is recorded by name and raw return code.

## Rules

- The host never executes the binary. CI never executes the binary.
- The guest never receives the provider key, the source directory or client data.
- The original and the candidate run on the same corpus and the same environment.
- The observation is raw data; the verifier interprets it against the contract.
