#!/usr/bin/env python3
"""Run the original and a candidate in a disposable WSL2 guest.

The host only orchestrates WSL commands. It copies the ELFs and corpus into a
fresh directory inside the guest, runs ``run_cases.py`` twice through argv (no
shell), pulls the observation files back, and records the guest environment.

Exit codes:
    0  ok
    2  bad host input (missing file, not ELF64 x86-64, unreadable corpus)
    3  guest failure (no WSL/distro, timeout, copy/run failure)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

Runner = Callable[..., subprocess.CompletedProcess[str]]
Copier = Callable[[str, Path, str, float, Runner], None]


class GuestFailure(Exception):
    """A guest-side failure with a stable, machine-readable code."""

    def __init__(self, code: str, detail: str, exit_code: int = 3) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.exit_code = exit_code


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_elf64(path: Path) -> None:
    data = path.read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError(f"{path} is not an ELF file")
    if len(data) < 20 or data[4] != 2 or data[5] != 1:
        raise ValueError(f"{path} is not little-endian ELF64")
    if int.from_bytes(data[18:20], "little") != 62:
        raise ValueError(f"{path} is not EM_X86_64")


def _wsl_path(path: Path) -> str:
    """Map a Windows path to the /mnt/<drive>/... path visible in WSL."""
    resolved = path.resolve()
    drive = resolved.drive
    if not drive or len(drive) != 2 or drive[1] != ":":
        raise ValueError(f"cannot map a non-Windows path into WSL: {path}")
    parts = [part for part in resolved.parts[1:] if part not in ("", "\\")]
    return "/mnt/" + drive[0].lower() + "/" + "/".join(
        part.replace("\\", "/") for part in parts
    )


def _run(
    distro: str,
    argv: list[str],
    timeout: float,
    runner: Runner,
) -> subprocess.CompletedProcess[str]:
    """Invoke one guest command with argv; never use shell interpolation."""
    cmd = ["wsl.exe", "-d", distro, "-e", *argv]
    try:
        completed = runner(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GuestFailure("guest_unavailable", f"wsl.exe not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GuestFailure("guest_timeout", f"guest command timed out: {argv[0]}") from exc
    except OSError as exc:
        raise GuestFailure("guest_unavailable", str(exc)) from exc
    if completed.returncode != 0:
        raise GuestFailure(
            "guest_command_failed",
            (completed.stderr or completed.stdout or "guest command failed").strip(),
        )
    return completed


def _copy_in(
    source: Path,
    destination: str,
    distro: str,
    timeout: float,
    runner: Runner,
) -> None:
    _run(
        distro,
        ["cp", _wsl_path(source), destination],
        timeout,
        runner,
    )


def _copy_out(
    source: str,
    destination: Path,
    distro: str,
    timeout: float,
    runner: Runner,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        distro,
        ["cp", source, _wsl_path(destination)],
        timeout,
        runner,
    )


def _guest_environment(distro: str, timeout: float, runner: Runner) -> dict[str, Any]:
    code = (
        "import json,platform;"
        "print(json.dumps({'uname':' '.join(platform.uname()),"
        "'kernel':platform.release(),"
        "'libc':platform.libc_ver()[0]+' '+platform.libc_ver()[1]}))"
    )
    completed = _run(distro, ["python3", "-c", code], timeout, runner)
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GuestFailure("guest_environment_invalid", completed.stdout.strip()) from exc
    try:
        version = runner(
            ["wsl.exe", "--version"],
            capture_output=True,
            text=False,
            timeout=timeout,
            check=False,
        )
        raw_version = version.stdout
        if isinstance(raw_version, bytes):
            try:
                raw_version = raw_version.decode("utf-16-le")
            except UnicodeDecodeError:
                raw_version = raw_version.decode("utf-8", errors="replace")
        wsl_version = (raw_version or "").strip().splitlines()[:1]
        wsl_version = wsl_version[0].strip("\ufeff\x00 ") if wsl_version else None
    except (OSError, subprocess.TimeoutExpired):
        wsl_version = None
    return {
        "distro": distro,
        "uname": parsed.get("uname"),
        "kernel": parsed.get("kernel"),
        "libc": parsed.get("libc"),
        "wsl_version": wsl_version,
    }


def run_live_guest(
    *,
    original: Path,
    candidate: Path,
    cases: Path,
    out_dir: Path,
    distro: str = "Ubuntu",
    timeout: float = 120.0,
    keep: bool = False,
    runner: Runner = subprocess.run,
    copier: Copier = _copy_out,
) -> dict[str, Any]:
    """Run both ELFs in the guest and return the evidence summary."""
    for label, path in (("original", original), ("candidate", candidate)):
        if not path.is_file():
            raise GuestFailure(f"{label}_missing", f"{label} not found: {path}", 2)
        try:
            _check_elf64(path)
        except ValueError as exc:
            raise GuestFailure(f"{label}_invalid", str(exc), 2) from exc
    if not cases.is_file():
        raise GuestFailure("cases_missing", f"cases not found: {cases}", 2)
    try:
        corpus = json.loads(cases.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuestFailure("cases_invalid", str(exc), 2) from exc
    if not isinstance(corpus, dict) or not isinstance(corpus.get("cases"), list):
        raise GuestFailure("cases_invalid", "cases.json has no cases[]", 2)

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    guest_dir = f"/tmp/binaryrepair-{uuid.uuid4().hex}"
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        _run(distro, ["mkdir", "-p", f"{guest_dir}/original/cases"], timeout, runner)
        _run(distro, ["mkdir", "-p", f"{guest_dir}/candidate/cases"], timeout, runner)

        _copy_in(original, f"{guest_dir}/original/vuln.elf", distro, timeout, runner)
        _copy_in(candidate, f"{guest_dir}/candidate/vuln.elf", distro, timeout, runner)
        _copy_in(cases, f"{guest_dir}/original/cases/cases.json", distro, timeout, runner)
        _copy_in(cases, f"{guest_dir}/candidate/cases/cases.json", distro, timeout, runner)
        poc = cases.parent / "poc.txt"
        if poc.is_file():
            _copy_in(poc, f"{guest_dir}/original/cases/poc.txt", distro, timeout, runner)
            _copy_in(poc, f"{guest_dir}/candidate/cases/poc.txt", distro, timeout, runner)

        runner_script = Path(__file__).with_name("run_cases.py")
        _copy_in(runner_script, f"{guest_dir}/run_cases.py", distro, timeout, runner)
        _run(
            distro,
            [
                "chmod",
                "+x",
                f"{guest_dir}/original/vuln.elf",
                f"{guest_dir}/candidate/vuln.elf",
                f"{guest_dir}/run_cases.py",
            ],
            timeout,
            runner,
        )

        for label in ("original", "candidate"):
            _run(
                distro,
                [
                    "python3",
                    f"{guest_dir}/run_cases.py",
                    "--fixture",
                    f"{guest_dir}/{label}",
                    "--out",
                    f"{guest_dir}/{label}-observations.json",
                ],
                timeout,
                runner,
            )
            copier(
                f"{guest_dir}/{label}-observations.json",
                out_dir / f"observations-{label}.json",
                distro,
                timeout,
                runner,
            )

        environment = _guest_environment(distro, timeout, runner)
        environment["started_at"] = started_at
        env_path = out_dir / "guest-environment.json"
        env_path.write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
        observations = {
            label: out_dir / f"observations-{label}.json"
            for label in ("original", "candidate")
        }
        return {
            "ok": True,
            "distro": distro,
            "started_at": started_at,
            "guest_dir": guest_dir,
            "kept": keep,
            "observations": {
                label: {
                    "path": str(path),
                    "sha256": _sha256(path),
                    "candidate_sha256": json.loads(path.read_text(encoding="utf-8"))[
                        "binary"
                    ]["sha256"],
                }
                for label, path in observations.items()
            },
            "environment": environment,
        }
    finally:
        if not keep:
            try:
                _run(distro, ["rm", "-rf", guest_dir], timeout, runner)
            except GuestFailure:
                pass


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--distro", default=os.environ.get("BINARYREPAIR_WSL_DISTRO", "Ubuntu")
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--keep", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_live_guest(
            original=args.original,
            candidate=args.candidate,
            cases=args.cases,
            out_dir=args.out_dir,
            distro=args.distro,
            timeout=args.timeout,
            keep=args.keep,
        )
    except GuestFailure as exc:
        print(f"{exc.code}: {exc.detail}", file=sys.stderr)
        return exc.exit_code
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
