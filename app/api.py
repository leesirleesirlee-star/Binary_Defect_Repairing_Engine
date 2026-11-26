"""Browser API and SSE journal for the S3 conversation console.

The GUI app reads persisted task metadata and the append-only event journal; it
does not import pipeline modules and never derives a verdict.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import os
import secrets
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, unquote

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app import assistant, assistant_client, assistant_key, g4, journal, live_audit, tasks
from app.journal import JournalError, read_records, wait_for_records
from app.preview_events import ensure_preview_journal

SESSION_COOKIE = "br_session"
CSRF_HEADER = "x-csrf-token"

# The real provider client is injected here.  Without a key/provider the assistant
# returns its deterministic fallback and the UI badge says so.
ASSISTANT_CLIENT: assistant.Client | None = assistant_client.complete
_BASE = Path(__file__).resolve().parent.parent
_SESSION_FILE = _BASE / "var" / "session.token"


def _session_token() -> str:
    configured = os.environ.get("BINARYREPAIR_SESSION_TOKEN")
    if configured:
        return configured
    try:
        if _SESSION_FILE.exists():
            stored = _SESSION_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        token = secrets.token_urlsafe(32)
        _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSION_FILE.write_text(token, encoding="utf-8")
        return token
    except OSError:
        return secrets.token_urlsafe(32)


SESSION_TOKEN = _session_token()
CSRF_TOKEN = hmac.new(SESSION_TOKEN.encode(), b"gui-csrf", hashlib.sha256).hexdigest()

router = APIRouter(prefix="/api")


def _error(status: int, code: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, **extra})


def append_gui_event(task_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    from app.journal import append_event

    return append_event(task_id, event_type, payload, source="gui")


def require_session(request: Request) -> None:
    if request.cookies.get(SESSION_COOKIE) != SESSION_TOKEN:
        raise _error(401, "session_required")


def require_csrf(
    request: Request, token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None
) -> None:
    if not token or not hmac.compare_digest(token, CSRF_TOKEN):
        raise _error(403, "request_forbidden")


def _task(task_id: str) -> dict[str, Any]:
    try:
        task = tasks.get(task_id)
    except tasks.TaskNotFound as error:
        raise _error(404, "not_found") from error
    try:
        records = read_records(task_id)
    except JournalError:
        records = []
    terminal = next((record for record in reversed(records) if record["type"] == "run_end"), None)
    if terminal and not (task.get("execution") or {}).get("terminal"):
        execution = task.get("execution") or {}
        execution.update(
            {
                "status": terminal["payload"].get("execution") or "failed",
                "terminal": True,
            }
        )
        tasks.set_execution(task_id, execution)
        task = tasks.get(task_id)
    return task


_ARTIFACT_ROOT = _BASE / "var" / "artifacts"


def _artifact_dir(task_id: str) -> Path:
    if not task_id or "/" in task_id or ".." in task_id:
        raise _error(404, "artifact_unavailable")
    return _ARTIFACT_ROOT / task_id


def _artifact_info(task_id: str, path: Path) -> dict[str, Any]:
    relative = path.relative_to(_ARTIFACT_ROOT).as_posix()
    encoded = quote(relative, safe="")
    return {
        "artifact_id": encoded,
        "display_path": path.relative_to(_artifact_dir(task_id)).as_posix(),
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
        "metadata_url": "/api/artifacts/" + encoded,
        "download_url": "/api/artifacts/" + encoded + "/download",
    }


def _artifact_path(artifact_id: str) -> Path:
    # artifact_id is the URL-encoded ``task_id/display_path`` and always stays
    # below var/artifacts; path traversal is rejected before any filesystem use.
    relative = unquote(artifact_id)
    candidate = (_ARTIFACT_ROOT / relative).resolve()
    root = _ARTIFACT_ROOT.resolve()
    if candidate != root and root not in candidate.parents:
        raise _error(404, "artifact_unavailable")
    if candidate == root or not candidate.is_file():
        raise _error(404, "artifact_unavailable")
    return candidate


@router.get("/session")
def session() -> JSONResponse:
    response = JSONResponse({"session": True, "csrf_token": CSRF_TOKEN})
    response.set_cookie(
        SESSION_COOKIE, SESSION_TOKEN, httponly=True, samesite="lax", secure=False, path="/"
    )
    return response


_IS_WINDOWS = os.name == "nt"


def _process_alive_windows(pid: int) -> bool:
    """Probe a Windows process without signalling it.

    ``os.kill(pid, 0)`` is not a probe on Windows: CPython maps every signal
    except CTRL_C_EVENT/CTRL_BREAK_EVENT to TerminateProcess, so the previous
    implementation killed the very repair runner it was inspecting.
    """
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    get_exit_code = kernel32.GetExitCodeProcess
    get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    get_exit_code.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not get_exit_code(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        close_handle(handle)


def _process_alive(pid: Any) -> bool:
    """Return whether ``pid`` is a live process, without signalling it."""
    try:
        value = int(pid)
        if value <= 0:
            return False
        if _IS_WINDOWS:
            return _process_alive_windows(value)
        os.kill(value, 0)
        return True
    except (OSError, OverflowError, TypeError, ValueError):
        return False


@router.get("/tasks", dependencies=[Depends(require_session)])
def list_tasks(limit: int = 50) -> dict[str, Any]:
    rows = tasks.list_tasks(limit)
    for task in rows:
        live = task.get("live_audit")
        if isinstance(live, dict) and live.get("status") == "running" \
                and not live_audit.is_active(task["id"]):
            task["live_audit"] = {**live, "status": "stale"}
        execution = task.get("execution")
        if isinstance(execution, dict) and execution.get("status") == "running" \
                and not _process_alive(execution.get("pid")):
            task["execution"] = {**execution, "status": "stale", "terminal": True}
    return {"tasks": rows}


@router.post(
    "/tasks", status_code=201, dependencies=[Depends(require_session), Depends(require_csrf)]
)
def create_task(body: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    payload = body or {}
    preview = bool(payload.get("preview"))
    task = tasks.create(preview=preview)
    if preview:
        task["phase"] = "preview"
        tasks.update(task)
        ensure_preview_journal(task["id"])
    return {"id": task["id"], "phase": task["phase"]}


@router.get("/assistant/key", dependencies=[Depends(require_session)])
def assistant_key_status() -> dict[str, Any]:
    """Masked provider-key status; the key itself never crosses this boundary."""
    return {"key": assistant_key.key_status(), "assistant": assistant_key.assistant_status()}


@router.post("/assistant/key", dependencies=[Depends(require_session), Depends(require_csrf)])
def assistant_key_save(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    candidate = body.get("key")
    if not isinstance(candidate, str) or not candidate.strip():
        raise _error(422, "key_required")
    try:
        saved = assistant_key.save_key(candidate)
    except assistant_key.KeyError as error:
        status = 409 if "environment" in str(error) else 422
        raise _error(status, "key_rejected", detail=str(error)) from error
    return {
        "saved": saved,
        "key": assistant_key.key_status(),
        "assistant": assistant_key.assistant_status(),
    }


@router.post("/assistant/key/test", dependencies=[Depends(require_session), Depends(require_csrf)])
def assistant_key_test(body: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    payload = body or {}
    return assistant_key.test_connection(payload.get("model"))


@router.delete("/assistant/key", dependencies=[Depends(require_session), Depends(require_csrf)])
def assistant_key_clear() -> dict[str, Any]:
    try:
        assistant_key.clear_key()
    except assistant_key.KeyError as error:
        raise _error(409, "key_managed", detail=str(error)) from error
    return {"key": assistant_key.key_status(), "assistant": assistant_key.assistant_status()}


@router.get("/tasks/{task_id}/journal", dependencies=[Depends(require_session)])
def task_journal(task_id: str, after_seq: int | None = None) -> dict[str, Any]:
    """Persisted GUI journal for one task; read-only and replayable by seq."""
    try:
        tasks.get(task_id)
    except KeyError:
        raise _error(404, "task_not_found") from None
    records = journal.read_records(task_id)
    if after_seq is None:
        records = records[-300:]
    else:
        records = [record for record in records if record.get("seq", 0) > after_seq]
    return {"records": records, "last_seq": records[-1]["seq"] if records else (after_seq or 0)}


@router.get("/g4/g2", dependencies=[Depends(require_session)])
def g4_g2() -> dict[str, Any]:
    """Read-only signed G2 audit, decision and selected plan (no re-vote)."""
    return g4.g2_payload()


@router.get("/g4/fixture", dependencies=[Depends(require_session)])
def g4_fixture() -> dict[str, Any]:
    """Frozen demo binary + oracle cases for the console's one-click demo."""
    return g4.fixture_payload()


@router.post(
    "/tasks/upload",
    status_code=201,
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def upload_task(body: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    """Upload an ELF plus its cases; analyze it and offer repair contracts."""
    payload = body or {}
    try:
        return g4.create_task(
            binary_name=payload.get("binary_name"),
            binary_base64=payload.get("binary_base64"),
            case_files=payload.get("case_files"),
            defect=payload.get("defect"),
        )
    except g4.G4Error as error:
        raise _error(error.status, error.code, **error.extra) from error


@router.post(
    "/tasks/probe",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def probe_binary(body: Annotated[dict[str, Any] | None, Body()] = None) -> dict[str, Any]:
    """Recognize an uploaded ELF first; case files are requested afterwards."""
    payload = body or {}
    try:
        return g4.probe_binary(
            binary_name=payload.get("binary_name"),
            binary_base64=payload.get("binary_base64"),
        )
    except g4.G4Error as error:
        raise _error(error.status, error.code, **error.extra) from error


@router.get("/tasks/{task_id}/g4", dependencies=[Depends(require_session)])
def task_g4(task_id: str) -> dict[str, Any]:
    _task(task_id)
    try:
        return g4.get_task_g4(task_id)
    except g4.G4Error as error:
        raise _error(error.status, error.code, **error.extra) from error


@router.post(
    "/tasks/{task_id}/g4/select",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def select_g4_option(task_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    _task(task_id)
    try:
        return g4.select_option(task_id, body.get("option_id"))
    except g4.G4Error as error:
        raise _error(error.status, error.code, **error.extra) from error


@router.get("/tasks/{task_id}", dependencies=[Depends(require_session)])
def get_task(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    task.pop("idempotency", None)
    return task


@router.delete(
    "/tasks/{task_id}",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def delete_task(task_id: str) -> dict[str, Any]:
    """Delete one task snapshot and every journal/artifact derived from it."""
    _task(task_id)
    try:
        tasks.delete(task_id)
    except tasks.TaskNotFound as error:
        raise _error(404, "task_not_found") from error
    base = _BASE / "var"
    for path in (
        base / "events" / f"{task_id}.jsonl",
        base / "artifacts" / task_id,
        base / "uploads" / task_id,
        base / "audit" / task_id,
    ):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    return {"deleted": task_id}


@router.get("/tasks/{task_id}/audit", dependencies=[Depends(require_session)])
def live_audit_state(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    live = task.get("live_audit") or live_audit.empty_state()
    # Re-evaluate persisted runs against the current edit budget so a policy
    # fix (for example allowing guard_stub) applies without rerunning the model.
    runs = live.get("runs") if isinstance(live, dict) else None
    if isinstance(runs, list):
        live = {**live, "runs": [
            {**run,
             "selectable": live_audit._plan_selectability(task, run.get("plan"))[0],
             "select_reason": live_audit._plan_selectability(task, run.get("plan"))[1]}
            if isinstance(run, dict) else run
            for run in runs
        ]}
    return {
        "audit_mode": task.get("audit_mode") or "signed",
        "live_guest": bool(task.get("live_guest")),
        "live_audit": live,
        "selected_plan": task.get("selected_plan"),
        "guest_available": live_audit.GUEST_AVAILABLE,
    }


@router.post(
    "/tasks/{task_id}/audit/live",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def start_live_audit(task_id: str, body: Annotated[dict[str, Any] | None, Body()] = None) -> Any:
    _task(task_id)
    try:
        result = live_audit.start(task_id, rerun=bool((body or {}).get("rerun")))
    except live_audit.LiveAuditError as error:
        raise _error(error.status, error.code, **error.extra) from error
    return JSONResponse(status_code=202, content=result)


@router.post(
    "/tasks/{task_id}/audit/signed",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def reset_live_audit(task_id: str) -> dict[str, Any]:
    _task(task_id)
    try:
        return live_audit.reset_signed(task_id)
    except live_audit.LiveAuditError as error:
        raise _error(error.status, error.code, **error.extra) from error


@router.post(
    "/tasks/{task_id}/audit/guest",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def set_live_guest(task_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    _task(task_id)
    try:
        return live_audit.set_guest(task_id, bool((body or {}).get("enabled")))
    except live_audit.LiveAuditError as error:
        raise _error(error.status, error.code, **error.extra) from error


@router.post(
    "/tasks/{task_id}/plan",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def select_live_plan(task_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    _task(task_id)
    try:
        result = live_audit.select_plan(task_id, body)
    except live_audit.LiveAuditError as error:
        raise _error(error.status, error.code, **error.extra) from error
    task = _task(task_id)
    selected = result["selected_plan"]
    decision = {
        "decision": "proceed",
        "decided_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "binding_digest": task.get("review_binding_digest"),
        "selected_plan_sha256": selected["canonical_sha256"],
    }
    task["decision"] = decision
    tasks.update(task)
    append_gui_event(task_id, "user_response", {
        "request_id": "live-plan", "kind": "plan_selection", **selected,
    })
    return {"selected_plan": selected, "decision": decision}


@router.get("/tasks/{task_id}/contract", dependencies=[Depends(require_session)])
def get_contract(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    return {
        "contract": task["contract"],
        "revision": task["contract_revision"],
        "sha256": task["contract_sha256"],
        "review_binding_digest": task["review_binding_digest"],
    }


@router.put(
    "/tasks/{task_id}/contract", dependencies=[Depends(require_session), Depends(require_csrf)]
)
def update_contract(task_id: str, body: Annotated[dict[str, Any], Body()]) -> None:
    _task(task_id)
    # The frozen G1 contract cannot be edited in place; a new freeze is a new task.
    raise _error(409, "frozen_contract")


@router.post(
    "/tasks/{task_id}/approve", dependencies=[Depends(require_session), Depends(require_csrf)]
)
def approve_task(task_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    task = _task(task_id)
    selected = task.get("selected_plan") or {}
    expected_plan = str(body.get("expected_plan_sha256") or "")
    if selected:
        if expected_plan != selected.get("canonical_sha256"):
            raise _error(409, "plan_not_approved",
                         expected_plan_sha256=selected.get("canonical_sha256"))
    try:
        approval = tasks.approve(
            task_id,
            str(body.get("expected_review_binding_digest") or ""),
            str(body.get("reviewer_label") or "M2"),
            plan_sha256=selected.get("canonical_sha256"),
        )
    except ValueError as error:
        raise _error(
            409, "stale_approval", current_binding_digest=_task(task_id)["review_binding_digest"]
        ) from error
    return approval


@router.post(
    "/tasks/{task_id}/decision", dependencies=[Depends(require_session), Depends(require_csrf)]
)
def decide_task(task_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """Record a G2 decision in the journal and the task snapshot.

    The runner prefers the persisted snapshot decision; writing both before the
    Start call closes the GUI/runner journal-append race without a second runner
    change (issue #53).
    """
    task = _task(task_id)
    if not (task.get("approval") or {}).get("approved"):
        raise _error(409, "approval_required")
    decision = str(body.get("decision") or "")
    if decision not in {"proceed", "iterate", "change_scope"}:
        raise _error(422, "invalid_decision")
    binding_digest = task.get("review_binding_digest")
    if not isinstance(binding_digest, str) or not binding_digest:
        raise _error(409, "approval_required")
    decided_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    record_value = {
        "decision": decision,
        "decided_at": decided_at,
        "binding_digest": binding_digest,
    }
    request_id = str(body.get("request_id") or "decision")
    record = append_gui_event(
        task_id,
        "user_response",
        {
            "request_id": request_id,
            "kind": "audit_decision",
            **record_value,
        },
    )
    tasks.update({**task, "decision": record_value})
    return {"decision": decision, "seq": record["seq"], **record_value}


@router.post(
    "/tasks/{task_id}/start", dependencies=[Depends(require_session), Depends(require_csrf)]
)
def start_task(
    task_id: str,
    body: Annotated[dict[str, Any], Body()],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    task = _task(task_id)
    if task.get("demo"):
        raise _error(409, "preview_only")
    if not idempotency_key:
        raise _error(400, "idempotency_key_required")
    selected = task.get("selected_plan") or {}
    if selected and (task.get("approval") or {}).get("plan_sha256") != selected.get(
            "canonical_sha256"):
        raise _error(409, "plan_not_approved")
    previous = dict(task.get("idempotency") or {})
    try:
        acknowledgement = tasks.begin_start(
            task_id,
            str(body.get("expected_review_binding_digest") or ""),
            idempotency_key,
        )
    except ValueError as error:
        raise _error(409, "stale_approval") from error
    except PermissionError as error:
        raise _error(409, "approval_required") from error
    if idempotency_key in previous:
        # Same key replays the original acknowledgement; never spawn a second runner.
        return acknowledgement
    runner = _BASE / "scripts" / "run_task.py"
    if not runner.is_file():
        tasks.set_execution(
            task_id,
            {
                "run_id": acknowledgement["run_id"],
                "status": "blocked",
                "terminal": True,
                "reason_code": "runner_unavailable",
            },
        )
        raise _error(503, "runner_unavailable", run_id=acknowledgement["run_id"])
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "scripts.run_task",
                "--task",
                task_id,
                "--var-root",
                str(_BASE / "var"),
                "--repo-root",
                str(_BASE),
            ],
            cwd=_BASE,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        tasks.set_execution(
            task_id,
            {
                "run_id": acknowledgement["run_id"],
                "status": "blocked",
                "terminal": True,
                "reason_code": "runner_unavailable",
            },
        )
        raise _error(503, "runner_unavailable") from error
    execution = task.get("execution") or {}
    execution.update(
        {
            "run_id": acknowledgement["run_id"],
            "status": "queued",
            "terminal": False,
            "pid": process.pid,
        }
    )
    tasks.set_execution(task_id, execution)
    return {"run_id": acknowledgement["run_id"], "phase": "queued"}


@router.post(
    "/tasks/{task_id}/cancel", dependencies=[Depends(require_session), Depends(require_csrf)]
)
def cancel_task(
    task_id: str, body: Annotated[dict[str, Any], Body()] | None = None
) -> dict[str, Any]:
    task = _task(task_id)
    execution = task.get("execution") or {}
    run_id = (body or {}).get("run_id") or execution.get("run_id")
    if not run_id or execution.get("run_id") != run_id:
        raise _error(409, "invalid_transition")
    execution.update({"status": "cancelled", "terminal": True, "reason_code": "user_cancelled"})
    tasks.set_execution(task_id, execution)
    return {"run_id": run_id, "phase": "cancelled", "execution": execution}


def _sse(record: dict[str, Any]) -> str:
    event_type = str(record["type"])
    data = json.dumps(record, ensure_ascii=True, separators=(",", ":"))
    return f"id: {record['seq']}\nevent: {event_type}\ndata: {data}\n\n"


_LIVE_STATUSES = {"queued", "waiting_for_executor", "running", "cancelling"}


def _task_can_stream(task: dict[str, Any]) -> bool:
    """A task that is no longer running cannot append more journal records.

    The stream must close instead of holding a browser connection open forever:
    browsers cap concurrent connections per origin, so a handful of idle SSE
    streams starve every other tab on the same host.
    """
    execution = task.get("execution") or {}
    status = str(execution.get("status") or task.get("phase") or "")
    return not execution.get("terminal") and status in _LIVE_STATUSES


@router.get("/tasks/{task_id}/events", dependencies=[Depends(require_session)])
async def task_events(
    task_id: str,
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
):
    task = _task(task_id)
    if task.get("demo"):
        ensure_preview_journal(task_id)
    try:
        last = int(last_event_id) if last_event_id else 0
    except ValueError as error:
        raise _error(400, "invalid_last_event_id") from error
    if last < 0:
        raise _error(400, "invalid_last_event_id")

    async def stream():
        nonlocal last
        while True:
            try:
                records = await asyncio.to_thread(read_records, task_id, after_seq=last)
            except JournalError:
                yield 'event: journal_gap\ndata: {"code":"journal_gap"}\n\n'
                return
            for record in records:
                last = record["seq"]
                yield _sse(record)
                if record["type"] == "run_end":
                    return
            try:
                current = await asyncio.to_thread(_task, task_id)
            except HTTPException:
                return
            if not _task_can_stream(current):
                return
            if await request.is_disconnected():
                return
            wait_started = asyncio.get_running_loop().time()
            try:
                records = await asyncio.to_thread(
                    wait_for_records, task_id, after_seq=last, timeout=15.0
                )
            except JournalError:
                yield 'event: journal_gap\ndata: {"code":"journal_gap"}\n\n'
                return
            for record in records:
                last = record["seq"]
                yield _sse(record)
                if record["type"] == "run_end":
                    return
            if not records and asyncio.get_running_loop().time() - wait_started >= 14.0:
                yield ": heartbeat\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _read_task_file(task_id: str, name: str) -> dict[str, Any] | None:
    path = _artifact_dir(task_id) / name
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


@router.get("/tasks/{task_id}/audit", dependencies=[Depends(require_session)])
def get_audit(task_id: str) -> dict[str, Any]:
    _task(task_id)
    return _read_task_file(task_id, "audit.json") or {"available": False}


@router.get("/tasks/{task_id}/manifest", dependencies=[Depends(require_session)])
def get_manifest(task_id: str) -> dict[str, Any]:
    _task(task_id)
    return _read_task_file(task_id, "edit-manifest.json") or {"available": False}


@router.get("/tasks/{task_id}/verdict", dependencies=[Depends(require_session)])
def get_verdict(task_id: str) -> dict[str, Any]:
    _task(task_id)
    value = _read_task_file(task_id, "verdict.json")
    if value is None:
        return {"available": False, "finalized": False}
    return {"available": True, "finalized": True, **value}


@router.get("/tasks/{task_id}/analysis", dependencies=[Depends(require_session)])
def get_analysis(task_id: str) -> dict[str, Any]:
    _task(task_id)
    view = _read_task_file(task_id, "disassembly.json")
    finding = _read_task_file(task_id, "finding.json")
    return {"available": bool(view and finding), "view": view, "finding": finding}


@router.get("/tasks/{task_id}/artifacts", dependencies=[Depends(require_session)])
def get_artifacts(task_id: str) -> dict[str, Any]:
    _task(task_id)
    directory = _artifact_dir(task_id)
    if not directory.is_dir():
        return {"artifacts": []}
    artifacts = [
        _artifact_info(task_id, path) for path in sorted(directory.iterdir()) if path.is_file()
    ]
    return {"artifacts": artifacts}


@router.get("/artifacts/{artifact_id:path}/download", dependencies=[Depends(require_session)])
def artifact_download(artifact_id: str) -> FileResponse:
    path = _artifact_path(artifact_id)
    task_id = path.relative_to(_ARTIFACT_ROOT).parts[0]
    _task(task_id)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


@router.get("/artifacts/{artifact_id:path}", dependencies=[Depends(require_session)])
def artifact(artifact_id: str) -> dict[str, Any]:
    path = _artifact_path(artifact_id)
    task_id = path.relative_to(_ARTIFACT_ROOT).parts[0]
    _task(task_id)
    return _artifact_info(task_id, path)


@router.get("/tasks/{task_id}/export", dependencies=[Depends(require_session)])
def export_task(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    task.pop("idempotency", None)
    audit = _read_task_file(task_id, "audit.json")
    manifest = _read_task_file(task_id, "edit-manifest.json")
    verdict = _read_task_file(task_id, "verdict.json")
    directory = _artifact_dir(task_id)
    artifacts = (
        [_artifact_info(task_id, path) for path in sorted(directory.iterdir()) if path.is_file()]
        if directory.is_dir()
        else []
    )
    return {
        "task": task,
        "audit": audit,
        "manifest": manifest,
        "verdict": verdict,
        "artifacts": artifacts,
    }


def _safe_task_json(relative: Any) -> dict[str, Any] | None:
    if not isinstance(relative, str) or not relative:
        return None
    path = (_BASE / relative).resolve()
    root = _BASE.resolve()
    if root not in path.parents or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _assistant_grounding(
    task_id: str, task: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Persisted, display-only evidence for grounded repair answers.

    This never exposes source, the hidden corpus, keys or provider diagnostics.
    """
    extra: dict[str, Any] = {}
    verdict = _read_task_file(task_id, "verdict.json")
    if verdict is not None:
        extra["verdict_detail"] = verdict
    manifest = _read_task_file(task_id, "edit-manifest.json")
    if manifest is not None:
        patch = manifest.get("patch_site")
        patch = patch if isinstance(patch, dict) else {}
        cave = manifest.get("cave")
        cave = cave if isinstance(cave, dict) else {}
        trampoline = manifest.get("trampoline")
        trampoline = trampoline if isinstance(trampoline, dict) else {}
        extra["edit_manifest"] = {
            "patch_site": patch,
            "cave": cave,
            "trampoline": {key: trampoline.get(key) for key in
                           ("entry_vaddr", "code_size", "message_size", "total_size",
                            "blob_sha256", "strcpy_plt_vaddr")},
            "edits": [
                {key: item.get(key) for key in
                 ("name", "vaddr", "file_offset", "size", "purpose")}
                for item in (manifest.get("edits") or []) if isinstance(item, dict)
            ],
            "invariants": manifest.get("invariants"),
        }
    selected = task.get("selected_plan")
    selected = selected if isinstance(selected, dict) else {}
    plan_path = selected.get("path") or task.get("plan")
    plan = _safe_task_json(plan_path)
    if plan is not None:
        extra["repair_plan"] = {
            "plan_id": plan.get("plan_id"),
            "strategy": plan.get("strategy"),
            "fixture_id": plan.get("fixture_id"),
            "diagnosis": plan.get("diagnosis"),
            "root_cause": plan.get("root_cause"),
            "invalid_path": plan.get("invalid_path"),
            "assumptions": plan.get("assumptions"),
            "stated_criteria_coverage": plan.get("stated_criteria_coverage"),
            "edits": [
                {key: item.get(key) for key in
                 ("kind", "address", "target", "size", "reason", "new_bytes", "original_bytes")}
                for item in (plan.get("edits") or []) if isinstance(item, dict)
            ],
        }
    finding = _read_task_file(task_id, "finding.json")
    if finding is not None:
        extra["analysis_finding"] = finding
    contract = task.get("contract")
    contract = contract if isinstance(contract, dict) else None
    if contract is not None:
        extra["contract"] = {key: contract.get(key) for key in
                             ("binary_sha256", "capacity_bytes", "max_valid_input_bytes",
                              "capacity_includes_terminator", "invalid_stderr", "fixture_id")}
    recent: list[dict[str, Any]] = []
    for record in records[-160:]:
        if not isinstance(record, dict):
            continue
        kind = record.get("type")
        if kind not in {"error", "run_state", "run_end", "verification", "command",
                        "file_change", "plan_update", "audit_runs", "corpus_update"}:
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if kind == "audit_runs":
            payload = {"runs": [
                {key: run.get(key) for key in
                 ("run_index", "score", "schema_valid", "selectable", "select_reason")}
                for run in (payload.get("runs") or []) if isinstance(run, dict)
            ]}
        elif kind == "plan_update":
            payload = {"steps": [
                {key: step.get(key) for key in ("step_id", "status")}
                for step in (payload.get("steps") or []) if isinstance(step, dict)
            ]}
        elif kind == "file_change":
            payload = {"stage": payload.get("stage"), "files": [
                {key: item.get(key) for key in ("display_path", "sha256")}
                for item in (payload.get("files") or []) if isinstance(item, dict)
            ]}
        text = json.dumps(payload, ensure_ascii=False)
        if len(text) > 1800:
            payload = {"truncated": text[:1800]}
        recent.append({"seq": record.get("seq"), "type": kind,
                       "step_id": record.get("step_id"), "payload": payload})
    extra["journal"] = recent
    try:
        directory = _artifact_dir(task_id)
        extra["artifacts"] = [
            {"name": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}
            for path in sorted(directory.iterdir()) if path.is_file()
        ] if directory.is_dir() else []
    except OSError:
        extra["artifacts"] = []
    extra["guest"] = {"guest_available": live_audit.GUEST_AVAILABLE,
                      "live_guest": bool(task.get("live_guest"))}
    return extra


@router.post(
    "/tasks/{task_id}/assistant",
    dependencies=[Depends(require_session), Depends(require_csrf)],
)
def assistant_turn(task_id: str, body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
    """One chat turn: validated envelope from the assistant (T3)."""
    task = _task(task_id)
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        raise _error(422, "invalid_message")
    if len(message) > assistant.MAX_MESSAGE_CHARS:
        raise _error(422, "message_too_long")
    locale = body.get("locale")
    locale = locale if isinstance(locale, str) and locale else "zh-Hans"
    requested_model = body.get("model")
    if requested_model in (None, "", "default"):
        requested_model = None
    if requested_model not in (None, "deepseek-flash", "deepseek-v4-pro"):
        raise _error(422, "invalid_model")
    try:
        records = read_records(task_id)
    except JournalError as error:
        raise _error(422, "journal_invalid") from error
    directory = _artifact_dir(task_id)
    artifacts = (
        [_artifact_info(task_id, path) for path in sorted(directory.iterdir()) if path.is_file()]
        if directory.is_dir()
        else []
    )
    verdict = _read_task_file(task_id, "verdict.json")
    if verdict is not None:
        task = {**task, "verdict": verdict}
    client = ASSISTANT_CLIENT
    if client is not None and requested_model is not None:
        try:
            if "model" in inspect.signature(client).parameters:
                client = partial(client, model=requested_model)
        except (TypeError, ValueError):
            pass
    extra = _assistant_grounding(task_id, task, records)
    response = assistant.respond(
        task, records, message, locale=locale, client=client, artifacts=artifacts,
        context_extra=extra,
    )
    response["requested_model"] = requested_model
    return response
