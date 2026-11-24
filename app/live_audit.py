"""G4.1 live-mode backend: run the three-run audit in the API host.

This module never computes a plan, a verdict or a score.  It spawns the audit
CLI as a child of the API host with the provider key only in that child's
environment, records the three run records in the task snapshot, and validates a
human-selected plan against the frozen contract's edit budget.  The key never
enters the task snapshot, the journal, the browser or a log.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from app import assistant_key, tasks

ROOT = Path(__file__).resolve().parent.parent
AUDIT_ROOT = ROOT / "var" / "audit"
FIXTURE_DIR = ROOT / "fixtures" / "stack-overflow-01"
MODEL = "deepseek-v4-pro"
TIMEOUT_S = 600
_RUNNING: dict[str, subprocess.Popen[bytes]] = {}
_LOCK = threading.Lock()


class LiveAuditError(Exception):
    def __init__(self, status: int, code: str, **extra: Any) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.extra = extra


def canonical_plan_sha256(plan: dict[str, Any]) -> str:
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _audit_dir(task_id: str) -> Path:
    return AUDIT_ROOT / task_id


def empty_state() -> dict[str, Any]:
    return {"status": "idle", "model": MODEL, "started_at": None, "finished_at": None,
            "error": None, "runs": []}


def state(task_id: str) -> dict[str, Any]:
    task = tasks.get(task_id)
    live = task.get("live_audit")
    return live if isinstance(live, dict) else empty_state()


def _hex_bytes(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    text = value.replace(" ", "")
    if len(text) % 2:
        return None
    try:
        bytes.fromhex(text)
    except ValueError:
        return None
    return len(text) // 2


def _allowed_plan_error(plan: Any) -> str | None:
    if not isinstance(plan, dict):
        return "plan_not_allowed"
    edits = plan.get("edits")
    if not isinstance(edits, list) or not edits:
        return "plan_not_allowed"
    redirects = 0
    code_bytes = 0
    data_bytes = 0
    for edit in edits:
        if not isinstance(edit, dict):
            return "plan_not_allowed"
        kind = edit.get("kind")
        size = _hex_bytes(edit.get("new_bytes", ""))
        if size is None:
            return "plan_not_allowed"
        if kind == "redirect_call":
            redirects += 1
            if size != 5:
                return "plan_not_allowed"
        elif kind == "code":
            code_bytes += size
        elif kind == "data":
            data_bytes += size
        else:
            return "plan_not_allowed"
        address = edit.get("address")
        if not isinstance(address, str) or not address.startswith("0x"):
            return "plan_not_allowed"
        try:
            int(address, 16)
        except ValueError:
            return "plan_not_allowed"
    if redirects != 1 or code_bytes > 256 or data_bytes > 64:
        return "plan_not_allowed"
    return None


def _validate_against_task(task: dict[str, Any], plan: Any) -> dict[str, Any]:
    error = _allowed_plan_error(plan)
    if error:
        raise LiveAuditError(409, error)
    assert isinstance(plan, dict)
    if plan.get("fixture_id") not in (None, task.get("fixture_id")):
        raise LiveAuditError(409, "plan_not_allowed")
    expected_contract = task.get("contract_sha256")
    if plan.get("contract_sha256") not in (None, expected_contract):
        raise LiveAuditError(409, "plan_not_allowed")
    return plan


def _spawn(command: list[str], env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command, cwd=ROOT, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _set_state(task_id: str, live: dict[str, Any], **task_updates: Any) -> None:
    task = tasks.get(task_id)
    task["live_audit"] = live
    task.update(task_updates)
    tasks.update(task)


def _watch(task_id: str, process: subprocess.Popen[bytes], summary_path: Path) -> None:
    try:
        try:
            returncode = process.wait(timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise LiveAuditError(409, "audit_failed", detail="timeout") from None
        live = state(task_id)
        if returncode != 0:
            live.update({"status": "failed", "finished_at": _now(),
                         "error": "audit_failed"})
            _set_state(task_id, live)
            return
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            runs = summary.get("runs") if isinstance(summary, dict) else None
        except (OSError, ValueError):
            runs = None
        if not isinstance(runs, list) or len(runs) != 3:
            live.update({"status": "failed", "finished_at": _now(),
                         "error": "audit_summary_invalid"})
            _set_state(task_id, live)
            return
        clean_runs: list[dict[str, Any]] = []
        for index, run in enumerate(runs):
            if not isinstance(run, dict):
                live.update({"status": "failed", "finished_at": _now(),
                             "error": "audit_summary_invalid"})
                _set_state(task_id, live)
                return
            plan = run.get("plan")
            plan_path = run.get("plan_path") or run.get("path")
            clean = {
                "run_index": run.get("run_index") or index + 1,
                "schema_valid": bool(run.get("schema_valid")),
                "plan_sha256": run.get("plan_sha256"),
                "plan_path": plan_path,
                "plan": plan if isinstance(plan, dict) else None,
                "usage": run.get("usage") if isinstance(run.get("usage"), dict) else {},
                "critical_errors": run.get("critical_errors") or [],
                "score": run.get("score"),
                "canonical_sha256": (canonical_plan_sha256(clean_plan)
                                     if isinstance((clean_plan := (run.get("plan")
                                         if isinstance(run.get("plan"), dict) else None)), dict)
                                     else None),
            }
            if clean["plan"] is None and isinstance(plan_path, str):
                try:
                    path = (ROOT / plan_path).resolve()
                    if path.is_file() and (AUDIT_ROOT.resolve() in path.parents):
                        clean["plan"] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    clean["plan"] = None
            clean_runs.append(clean)
        live.update({"status": "completed", "finished_at": _now(), "error": None,
                     "model": summary.get("model") or MODEL, "runs": clean_runs})
        _set_state(task_id, live)
    except LiveAuditError as error:
        live = state(task_id)
        live.update({"status": "failed", "finished_at": _now(), "error": error.code,
                     "detail": error.extra.get("detail")})
        _set_state(task_id, live)
    except Exception:
        live = state(task_id)
        live.update({"status": "failed", "finished_at": _now(), "error": "audit_failed"})
        _set_state(task_id, live)
    finally:
        with _LOCK:
            _RUNNING.pop(task_id, None)


def start(task_id: str, *, rerun: bool = False) -> dict[str, Any]:
    task = tasks.get(task_id)
    g4 = task.get("g4") or {}
    if not g4.get("supported"):
        raise LiveAuditError(409, "audit_unsupported")
    live = state(task_id)
    if live.get("status") == "running":
        raise LiveAuditError(409, "audit_running")
    if live.get("status") == "completed" and not rerun:
        return {"status": "completed", "live_audit": live}
    key = assistant_key.load_key()
    if not key:
        raise LiveAuditError(409, "audit_no_provider")
    directory = _audit_dir(task_id)
    raw_dir = directory / "raw"
    summary_path = directory / "summary.json"
    directory.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for stale in (summary_path,):
        try:
            stale.unlink()
        except OSError:
            pass
    live = {
        "status": "running",
        "model": MODEL,
        "started_at": _now(),
        "finished_at": None,
        "error": None,
        "runs": [],
    }
    task = tasks.get(task_id)
    task["audit_mode"] = "live"
    task["selected_plan"] = None
    task["live_audit"] = live
    tasks.update(task)
    command = [
        sys.executable, "-m", "app.live_audit_child",
        "--fixture-dir", str(FIXTURE_DIR.relative_to(ROOT)),
        "--runs", "3",
        "--raw-dir", str(raw_dir.relative_to(ROOT)),
        "--summary-out", str(summary_path.relative_to(ROOT)),
        "--model", MODEL,
    ]
    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = key
    env["DEEPSEEK_MODEL"] = MODEL
    try:
        process = _spawn(command, env)
    except OSError as error:
        live.update({"status": "failed", "finished_at": _now(), "error": "audit_failed"})
        _set_state(task_id, live)
        raise LiveAuditError(409, "audit_failed") from error
    with _LOCK:
        _RUNNING[task_id] = process
    threading.Thread(target=_watch, args=(task_id, process, summary_path),
                     name="live-audit-" + task_id, daemon=True).start()
    return {"status": "running"}


def wait_for_terminal(task_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        live = state(task_id)
        if live.get("status") not in {"running", "idle"}:
            return live
        time.sleep(0.05)
    return state(task_id)


def select_plan(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    task = tasks.get(task_id)
    if not (task.get("g4") or {}).get("supported"):
        raise LiveAuditError(409, "unsupported_binary_scope")
    live = state(task_id)
    if live.get("status") != "completed":
        raise LiveAuditError(409, "plan_not_allowed")
    runs = live.get("runs") or []
    requested_index = body.get("run_index")
    requested_path = body.get("plan_path")
    run = None
    if requested_index is not None:
        try:
            index = int(requested_index)
        except (TypeError, ValueError):
            raise LiveAuditError(422, "plan_unknown") from None
        run = next((item for item in runs if int(item.get("run_index") or 0) == index), None)
    elif isinstance(requested_path, str):
        run = next((item for item in runs if item.get("plan_path") == requested_path), None)
    if run is None:
        raise LiveAuditError(409, "plan_unknown")
    plan = run.get("plan")
    if not isinstance(plan, dict) and isinstance(run.get("plan_path"), str):
        path = (ROOT / run["plan_path"]).resolve()
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            plan = None
    if not isinstance(plan, dict):
        raise LiveAuditError(409, "plan_not_allowed")
    _validate_against_task(task, plan)
    canonical = canonical_plan_sha256(plan)
    directory = _audit_dir(task_id)
    directory.mkdir(parents=True, exist_ok=True)
    selected_path = directory / "selected-plan.json"
    payload = json.dumps(plan, sort_keys=True, indent=2) + "\n"
    selected_path.write_text(payload, encoding="utf-8")
    relative = selected_path.relative_to(ROOT).as_posix()
    file_sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    selected = {
        "source": "live",
        "run_index": run.get("run_index"),
        "path": relative,
        "file_sha256": file_sha,
        "canonical_sha256": canonical,
    }
    task = tasks.get(task_id)
    task["selected_plan"] = selected
    task["plan"] = relative
    task["phase"] = "plan_selected"
    if body.get("live_guest") is not None:
        task["live_guest"] = bool(body.get("live_guest"))
    tasks.update(task)
    return {"selected_plan": selected}
