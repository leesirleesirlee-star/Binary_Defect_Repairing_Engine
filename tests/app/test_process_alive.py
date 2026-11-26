"""Process liveness probes must never signal (or kill) the process they inspect.

`GET /api/tasks` calls `_process_alive` for every running task, so a probe that
uses `os.kill(pid, 0)` on Windows would terminate the repair runner it is
supposed to inspect (CPython's Windows `os.kill` maps signals to
TerminateProcess).  The Windows implementation probes with OpenProcess /
GetExitCodeProcess; this test spawns a real child and would fail on the old
implementation when executed on Windows.
"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from app import api


def _spawn_sleeper(seconds: float = 30.0) -> subprocess.Popen[bytes]:
    child = subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep({seconds})"],
    )
    deadline = time.monotonic() + 5
    while child.poll() is not None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert child.poll() is None, "sleeper child exited before the probe"
    return child


def test_process_alive_probe_does_not_kill_a_live_process() -> None:
    child = _spawn_sleeper()
    try:
        assert api._process_alive(child.pid) is True
        assert child.poll() is None, "the liveness probe must not terminate the process"
    finally:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive cleanup
            child.kill()
            child.wait()
    assert api._process_alive(child.pid) is False


@pytest.mark.parametrize("pid", [None, 0, -1, "not-a-pid", "0"])
def test_process_alive_rejects_invalid_pids(pid: object) -> None:
    assert api._process_alive(pid) is False


def test_process_alive_uses_the_windows_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_windows_probe(pid: int) -> bool:
        calls.append(pid)
        return True

    monkeypatch.setattr(api, "_IS_WINDOWS", True)
    monkeypatch.setattr(api, "_process_alive_windows", fake_windows_probe)
    assert api._process_alive(4321) is True
    assert calls == [4321]
