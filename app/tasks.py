"""Local task metadata for the S3 console API. No pipeline or verdict logic."""

from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.fixture import snapshot

TASK_ID = re.compile(r"^tsk_[a-f0-9]{24}$")
_TASK_ROOT = Path(__file__).resolve().parent.parent / "var" / "tasks"


class TaskNotFound(KeyError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _path(task_id: str) -> Path:
    if not TASK_ID.match(task_id):
        raise TaskNotFound(task_id)
    return _TASK_ROOT / f"{task_id}.json"


def _read(task_id: str) -> dict[str, Any]:
    path = _path(task_id)
    if not path.exists():
        raise TaskNotFound(task_id)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TaskNotFound(task_id)
    return value


def _write(task: dict[str, Any]) -> dict[str, Any]:
    path = _path(task["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(task, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return task


def create(*, preview: bool = False) -> dict[str, Any]:
    fixture = snapshot()
    task_id = "tsk_" + secrets.token_hex(12)
    task = {
        "id": task_id,
        "fixture_id": fixture["fixture_id"],
        "phase": "preview" if preview else "draft",
        "demo": bool(preview),
        "created_at": _now(),
        "contract": fixture["contract"],
        "contract_revision": fixture["contract_revision"],
        "contract_sha256": fixture["contract_sha256"],
        "corpus": fixture["corpus"],
        "binary": fixture["binary"],
        "review_binding_digest": fixture["review_binding_digest"],
        "approval": {"approved": False},
        "execution": {"run_id": None, "status": "idle", "terminal": False, "reason_code": None},
        "idempotency": {},
    }
    return _write(task)


def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
    _TASK_ROOT.mkdir(parents=True, exist_ok=True)
    tasks = []
    for path in sorted(
        _TASK_ROOT.glob("tsk_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tasks.append(
            {key: task.get(key) for key in ("id", "fixture_id", "phase", "created_at")}
            | {"verdict": task.get("verdict"), "demo": bool(task.get("demo"))}
        )
        if len(tasks) >= min(max(1, limit), 200):
            break
    return tasks


def get(task_id: str) -> dict[str, Any]:
    return _read(task_id)


def update(task: dict[str, Any]) -> dict[str, Any]:
    return _write(task)


def approve(
    task_id: str, expected_binding_digest: str, reviewer_label: str = "M2",
    plan_sha256: str | None = None,
) -> dict[str, Any]:
    task = _read(task_id)
    if expected_binding_digest != task["review_binding_digest"]:
        raise ValueError("stale_approval")
    if task["approval"].get("approved"):
        return task["approval"]
    task["approval"] = {
        "approved": True,
        "approved_at": _now(),
        "reviewer_label": reviewer_label or "M2",
        "binding_digest": task["review_binding_digest"],
    }
    if plan_sha256:
        task["approval"]["plan_sha256"] = plan_sha256
    _write(task)
    return task["approval"]


def begin_start(task_id: str, expected_binding_digest: str, idempotency_key: str) -> dict[str, Any]:
    task = _read(task_id)
    if expected_binding_digest != task["review_binding_digest"]:
        raise ValueError("stale_approval")
    if not task["approval"].get("approved"):
        raise PermissionError("approval_required")
    if idempotency_key in task["idempotency"]:
        return task["idempotency"][idempotency_key]
    run_id = "run_" + secrets.token_hex(12)
    acknowledgement = {"run_id": run_id, "phase": "queued"}
    task["idempotency"][idempotency_key] = acknowledgement
    task["execution"] = {
        "run_id": run_id,
        "status": "queued",
        "terminal": False,
        "reason_code": None,
    }
    task["phase"] = "queued"
    _write(task)
    return acknowledgement


def set_execution(task_id: str, execution: dict[str, Any]) -> dict[str, Any]:
    task = _read(task_id)
    task["execution"] = execution
    task["phase"] = execution.get("status") or task["phase"]
    _write(task)
    return task
