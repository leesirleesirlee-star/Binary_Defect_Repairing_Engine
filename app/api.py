"""Browser API and SSE journal for the S3 conversation console.

The GUI app reads persisted task metadata and the append-only event journal; it
does not import pipeline modules and never derives a verdict.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app import tasks
from app.journal import JournalError, read_records, wait_for_records
from app.preview_events import ensure_preview_journal

SESSION_COOKIE = "br_session"
CSRF_HEADER = "x-csrf-token"
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
        return tasks.get(task_id)
    except tasks.TaskNotFound as error:
        raise _error(404, "not_found") from error


@router.get("/session")
def session() -> JSONResponse:
    response = JSONResponse({"session": True, "csrf_token": CSRF_TOKEN})
    response.set_cookie(
        SESSION_COOKIE, SESSION_TOKEN, httponly=True, samesite="lax", secure=False, path="/"
    )
    return response


@router.get("/tasks", dependencies=[Depends(require_session)])
def list_tasks(limit: int = 50) -> dict[str, Any]:
    return {"tasks": tasks.list_tasks(limit)}


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


@router.get("/tasks/{task_id}", dependencies=[Depends(require_session)])
def get_task(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    task.pop("idempotency", None)
    return task


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
    _task(task_id)
    try:
        approval = tasks.approve(
            task_id,
            str(body.get("expected_review_binding_digest") or ""),
            str(body.get("reviewer_label") or "M2"),
        )
    except ValueError as error:
        raise _error(
            409, "stale_approval", current_binding_digest=_task(task_id)["review_binding_digest"]
        ) from error
    return approval


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
    # No runner is wired yet. Fail honestly instead of fabricating a run.
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


@router.get("/tasks/{task_id}/audit", dependencies=[Depends(require_session)])
def get_audit(task_id: str) -> dict[str, Any]:
    _task(task_id)
    return {"available": False}


@router.get("/tasks/{task_id}/manifest", dependencies=[Depends(require_session)])
def get_manifest(task_id: str) -> dict[str, Any]:
    _task(task_id)
    return {"available": False}


@router.get("/tasks/{task_id}/verdict", dependencies=[Depends(require_session)])
def get_verdict(task_id: str) -> dict[str, Any]:
    _task(task_id)
    return {"available": False, "finalized": False}


@router.get("/tasks/{task_id}/artifacts", dependencies=[Depends(require_session)])
def get_artifacts(task_id: str) -> dict[str, Any]:
    _task(task_id)
    return {"artifacts": []}


@router.get("/tasks/{task_id}/export", dependencies=[Depends(require_session)])
def export_task(task_id: str) -> dict[str, Any]:
    task = _task(task_id)
    task.pop("idempotency", None)
    return {"task": task, "verdict": None, "artifacts": []}


@router.get("/artifacts/{artifact_id}", dependencies=[Depends(require_session)])
def artifact(artifact_id: str) -> None:
    raise _error(404, "artifact_unavailable")


@router.get("/artifacts/{artifact_id}/download", dependencies=[Depends(require_session)])
def artifact_download(artifact_id: str) -> None:
    raise _error(404, "artifact_unavailable")
