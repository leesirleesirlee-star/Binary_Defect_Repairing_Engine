"""Unit tests for the WSL2 live guest driver.

CI has no WSL. These tests inject a fake runner/copier and check argv handling,
input validation, failure mapping and the evidence summary; they never execute an
ELF or call wsl.exe.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from guest import live_guest

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "stack-overflow-01"


class _Recorder:
    def __init__(self, *, fail: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        assert kwargs.get("shell") is not True
        if self.fail == "missing":
            raise FileNotFoundError("wsl.exe")
        if self.fail == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1)
        if self.fail == "command":
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        if cmd[:2] == ["wsl.exe", "--version"]:
            return subprocess.CompletedProcess(cmd, 0, "WSL 2.6.1\n", "")
        if "python3" in cmd and "-c" in cmd:
            payload = {
                "uname": "Linux guest 6.18 x86_64",
                "kernel": "6.18.0",
                "libc": "glibc 2.43",
            }
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _fake_copier(source: str, destination: Path, distro, timeout, runner) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "binary": {
            "path": "vuln.elf",
            "sha256": live_guest._sha256(FIXTURE / "vuln.elf"),
        },
        "cases": [],
    }
    destination.write_text(json.dumps(payload), encoding="utf-8")


def _run_fixture(tmp_path: Path, recorder: _Recorder | None = None):
    return live_guest.run_live_guest(
        original=FIXTURE / "vuln.elf",
        candidate=FIXTURE / "vuln.elf",
        cases=FIXTURE / "cases" / "cases.json",
        out_dir=tmp_path / "out",
        runner=recorder or _Recorder(),
        copier=_fake_copier,
    )


def test_wsl_path_maps_windows_drive() -> None:
    assert live_guest._wsl_path(Path("C:/Users/a b/x.elf")) == "/mnt/c/Users/a b/x.elf"


def test_missing_input_is_exit_2(tmp_path: Path) -> None:
    with pytest.raises(live_guest.GuestFailure) as exc:
        live_guest.run_live_guest(
            original=tmp_path / "missing.elf",
            candidate=FIXTURE / "vuln.elf",
            cases=FIXTURE / "cases" / "cases.json",
            out_dir=tmp_path / "out",
        )
    assert exc.value.exit_code == 2
    assert exc.value.code == "original_missing"


def test_invalid_elf_is_exit_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.elf"
    bad.write_bytes(b"not elf")
    with pytest.raises(live_guest.GuestFailure) as exc:
        live_guest.run_live_guest(
            original=bad,
            candidate=FIXTURE / "vuln.elf",
            cases=FIXTURE / "cases" / "cases.json",
            out_dir=tmp_path / "out",
        )
    assert exc.value.exit_code == 2
    assert exc.value.code == "original_invalid"


def test_success_uses_argv_and_returns_hashes(tmp_path: Path) -> None:
    recorder = _Recorder()
    result = _run_fixture(tmp_path, recorder)
    assert result["ok"] is True
    assert result["observations"]["original"]["candidate_sha256"] == live_guest._sha256(
        FIXTURE / "vuln.elf"
    )
    assert result["observations"]["candidate"]["sha256"]
    assert result["environment"]["kernel"] == "6.18.0"
    commands = [call for call in recorder.calls if call[:3] == ["wsl.exe", "-d", "Ubuntu"]]
    assert commands
    assert all(isinstance(call, list) for call in commands)
    assert any(
        call[4:6] == ["cp", live_guest._wsl_path(FIXTURE / "vuln.elf")]
        for call in commands
    )
    assert all(call[0] == "wsl.exe" for call in commands)


def test_timeout_maps_to_guest_timeout(tmp_path: Path) -> None:
    with pytest.raises(live_guest.GuestFailure) as exc:
        _run_fixture(tmp_path, _Recorder(fail="timeout"))
    assert exc.value.exit_code == 3
    assert exc.value.code == "guest_timeout"


def test_missing_wsl_maps_to_guest_unavailable(tmp_path: Path) -> None:
    with pytest.raises(live_guest.GuestFailure) as exc:
        _run_fixture(tmp_path, _Recorder(fail="missing"))
    assert exc.value.exit_code == 3
    assert exc.value.code == "guest_unavailable"


def test_guest_command_failure_maps_to_exit_3(tmp_path: Path) -> None:
    with pytest.raises(live_guest.GuestFailure) as exc:
        _run_fixture(tmp_path, _Recorder(fail="command"))
    assert exc.value.exit_code == 3
    assert exc.value.code == "guest_command_failed"
