#!/usr/bin/env python3
"""Run M3 fixture cases on a Linux guest and emit observations only.

This script must run inside the disposable Linux guest. It never decides
"verified"; it records exit code/signal/stdout/stderr for the verifier.

Usage:
    python3 guest/run_cases.py \
      --fixture fixtures/stack-overflow-01 \
      --out var/observations.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import signal
import struct
import subprocess
import sys
from pathlib import Path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_elf32(path: Path) -> None:
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    if data[4] != 1:
        raise ValueError("fixture must be ELF32")
    if data[5] != 1:
        raise ValueError("fixture must be little-endian")
    machine = struct.unpack_from("<H", data, 18)[0]
    if machine != 3:
        raise ValueError("fixture must be EM_386")
    e_type = struct.unpack_from("<H", data, 16)[0]
    if e_type != 2:
        raise ValueError("fixture must be ET_EXEC (no PIE)")


def _signal_name(returncode: int) -> str | None:
    if returncode >= 0:
        return None
    try:
        return signal.Signals(-returncode).name
    except ValueError:
        return f"SIG{-returncode}"


def _run_one(elf: Path, case: dict, timeout: float) -> dict:
    data = (elf.parent / case["path"]).read_bytes()
    try:
        proc = subprocess.run(
            [str(elf)],
            input=data,
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
    return {
        "path": case["path"],
        "kind": case["kind"],
        "length": len(data),
        "sha256": _sha(data),
        "exit_code": exit_code,
        "signal": _signal_name(exit_code) if exit_code is not None else None,
        "timed_out": timed_out,
        "stdout_sha256": _sha(stdout),
        "stderr_sha256": _sha(stderr),
        "stdout_preview": stdout[:200].decode("utf-8", "replace"),
        "stderr_preview": stderr[:200].decode("utf-8", "replace"),
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
    _check_elf32(elf)
    # A checkout may not preserve the executable bit; make it runnable.
    try:
        elf.chmod(elf.stat().st_mode | 0o111)
    except OSError:
        pass
    contract = json.loads((fixture / "contract.json").read_text(encoding="utf-8"))
    observations = []
    for case in contract["cases"]:
        observations.append(_run_one(elf, case, args.timeout))

    payload = {
        "schema_version": "m3-observations-v0",
        "fixture_id": contract["fixture_id"],
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "elf_sha256": _sha(elf.read_bytes()),
        "cases": observations,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fixture_id": payload["fixture_id"], "cases": len(observations)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
