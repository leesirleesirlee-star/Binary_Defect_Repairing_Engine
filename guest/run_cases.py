#!/usr/bin/env python3
"""Run M3 fixture cases on a Linux x86-64 guest; emit observations only.

The verifier, not this runner, decides pass/fail. The ELF is invoked with
execve-style argv (never a shell), and stdout/stderr are base64-encoded so the
evidence is byte-exact.

Usage:
    python3 guest/run_cases.py \
      --fixture fixtures/stack-overflow-01 \
      --out var/observations-original.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import platform
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_elf64(path: Path) -> None:
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    if data[4] != 2:
        raise ValueError("fixture must be ELF64")
    if data[5] != 1:
        raise ValueError("fixture must be little-endian")
    if struct.unpack_from("<H", data, 18)[0] != 62:
        raise ValueError("fixture must be EM_X86_64")
    if struct.unpack_from("<H", data, 16)[0] != 2:
        raise ValueError("fixture must be ET_EXEC (no PIE)")


def _signal_name(returncode: int) -> str | None:
    if returncode >= 0:
        return None
    try:
        return signal.Signals(-returncode).name
    except ValueError:
        return f"SIG{-returncode}"


def _run_one(elf: Path, case: dict, timeout: float) -> dict:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [str(elf), *case.get("argv", [])],
            input=case.get("stdin", "").encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        exit_code = proc.returncode
        timed_out = False
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        timed_out = True
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    elapsed = int((time.monotonic() - start) * 1000)
    return {
        "id": case["id"],
        "argv_sha256": _sha(json.dumps(case.get("argv", []), separators=(",", ":")).encode()),
        "exit_code": exit_code,
        "signal": _signal_name(exit_code) if exit_code is not None else None,
        "stdout_b64": base64.b64encode(stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(stderr).decode("ascii"),
        "duration_ms": elapsed,
        "timed_out": timed_out,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args(argv)

    if not sys.platform.startswith("linux"):
        print("run_cases.py must run on a Linux guest, not the host", file=sys.stderr)
        return 2

    fixture = args.fixture.resolve()
    elf = fixture / "vuln.elf"
    _check_elf64(elf)
    try:
        elf.chmod(elf.stat().st_mode | 0o111)
    except OSError:
        pass
    corpus = json.loads((fixture / "cases" / "cases.json").read_text(encoding="utf-8"))
    observations = [_run_one(elf, case, args.timeout) for case in corpus["cases"]]
    payload = {
        "schema_version": 1,
        "binary": {"path": "vuln.elf", "sha256": _sha(elf.read_bytes())},
        "environment": {
            "uname": " ".join(platform.uname()),
            "kernel": platform.release(),
            "libc": platform.libc_ver()[0] + " " + platform.libc_ver()[1],
        },
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cases": observations,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixture_id": corpus["fixture_id"], "cases": len(observations)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
