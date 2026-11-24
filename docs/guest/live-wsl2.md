# Live WSL2 guest driver (G4.1)

`guest/live_guest.py` is the host-side driver for the additive live mode. It
copies the original ELF, the candidate ELF and the frozen cases into a fresh
temporary directory **inside** the selected WSL distro, runs
`guest/run_cases.py` twice, pulls the two `ObservationV1` files and the guest
environment back to the host, and removes the guest directory unless `--keep`
is given. The host never executes an ELF.

## Usage

```bash
python guest/live_guest.py \
  --original fixtures/stack-overflow-01/vuln.elf \
  --candidate var/artifacts/<task>/candidate.elf \
  --cases fixtures/stack-overflow-01/cases/cases.json \
  --out-dir var/artifacts/<task>/live-guest \
  [--distro Ubuntu] [--timeout 120] [--keep]
```

`--distro` defaults to `BINARYREPAIR_WSL_DISTRO`, then `Ubuntu`.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Both observations and the environment were written. |
| `2` | Bad host input: missing file, not ELF64 x86-64, unreadable cases. |
| `3` | Guest failure: no WSL/distro, timeout, copy/run failure. |

The driver passes paths as argv to `wsl.exe ... -e`; it never builds a shell
command from a path.

## Outputs

```text
<out-dir>/observations-original.json
<out-dir>/observations-candidate.json
<out-dir>/guest-environment.json
```

`guest-environment.json` contains `distro`, `uname`, `kernel`, `libc`,
`wsl_version` and `started_at`.

## Real run on M3's WSL2

Host: Windows, `wsl --list --verbose` shows `Ubuntu` version 2. The guest was
freshly terminated before the run:

```powershell
wsl --terminate Ubuntu
```

The candidate was regenerated from `main` with the merged apply CLI and the G2
frozen plan; the candidate hash was:

```text
c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28
```

The driver run on this host printed:

```text
{"ok": true, "distro": "Ubuntu", "started_at": "2026-11-24T02:42:59Z",
 "observations": {"candidate": {"sha256": "23a25bde09ac2d345c446ddef32a81aede7ce908df128cce40a977392593332f",
                                 "candidate_sha256": "c010c006b573b29a683540d128296bc94343e0d0c8bf73fc2c308b95aaa25b28"}},
 "environment": {"distro": "Ubuntu", "kernel": "6.18.40.1-microsoft-standard-WSL2",
                 "libc": "glibc 2.43", "wsl_version": "WSL 版本: 3.0.1.0"}}
```

Observation file hashes include timing fields and therefore vary between runs;
the binding that matters is `binary.sha256 == c010c006...b28`. The merged
verifier consumed this run and returned `verified_against_stated_criteria` with
canonical verdict hash
`51f29be55aea38070029429b1102eb7a0ee1557dbf99b15cdce64440e5bec45c`.

Nine cases were recorded: valid cases exited 0 with `argv + LF`; invalid
32/33/64/128 exited 1 with empty stdout, the exact 42-byte `invalid_stderr`, and
no signal.

## Isolation limitation

WSL2 shares the host network and is not a dedicated disposable VM. This is a
weaker isolation claim than a Multipass/Hyper-V guest; it is recorded here and
must be carried into the G4.1 demo record. No credentials are copied into the
guest.

## Tests

`tests/guest/test_live_guest.py` injects a fake runner/copier; it never calls
WSL or executes an ELF, so CI remains WSL-free.
