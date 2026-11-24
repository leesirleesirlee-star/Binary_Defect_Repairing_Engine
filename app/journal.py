"""Append-only GUI event journal.

The GUI reads and validates `var/events/{task_id}.jsonl`; it does not import any
pipeline module. Only an explicit runner or the labelled preview writer should
append real/synthetic events.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TASK_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
EVENT_TYPES = {
    "user_message",
    "message_dispatched",
    "assistant_delta",
    "assistant_end",
    "thinking",
    "tool_call",
    "tool_result",
    "run_state",
    "plan_update",
    "corpus_update",
    "awaiting_user",
    "user_response",
    "file_change",
    "command",
    "verification",
    "audit_runs",
    "error",
    "run_end",
}
SOURCES = {"runner", "verifier", "gui", "synthetic"}
MAX_RECORD_BYTES = 1_000_000
_LOCK = threading.Lock()


class JournalError(ValueError):
    """The journal is malformed or an event violates the v1 envelope."""


class JournalGap(JournalError):
    """Replay requested a sequence that is not contiguous."""


def _root(root: Path | None = None) -> Path:
    return (
        Path(root)
        if root is not None
        else Path(__file__).resolve().parent.parent / "var" / "events"
    )


def journal_path(task_id: str, root: Path | None = None) -> Path:
    if not TASK_ID.match(task_id):
        raise JournalError("invalid task id")
    return _root(root) / f"{task_id}.jsonl"


def _validate(record: dict[str, Any], expected_seq: int | None = None) -> dict[str, Any]:
    required = {"version", "type", "conversation_id", "seq", "ts", "source", "payload"}
    missing = required - record.keys()
    if missing:
        raise JournalError(f"missing envelope fields: {sorted(missing)}")
    if record["version"] != 1:
        raise JournalError("unsupported envelope version")
    seq = record["seq"]
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise JournalError("seq must be a positive integer")
    if expected_seq is not None and seq != expected_seq:
        raise JournalGap(f"expected seq {expected_seq}, got {seq}")
    if record["type"] not in EVENT_TYPES:
        raise JournalError(f"unknown event type: {record['type']}")
    if record["source"] not in SOURCES:
        raise JournalError(f"unknown source: {record['source']}")
    if not isinstance(record["payload"], dict):
        raise JournalError("payload must be an object")
    if not isinstance(record["conversation_id"], str) or not record["conversation_id"]:
        raise JournalError("conversation_id is required")
    return record


def read_records(
    task_id: str, *, after_seq: int = 0, root: Path | None = None
) -> list[dict[str, Any]]:
    """Return validated records with seq > after_seq in order; gaps fail closed."""
    path = journal_path(task_id, root)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    expected = 1
    with path.open("rb") as handle:
        for raw in handle:
            if len(raw) > MAX_RECORD_BYTES:
                raise JournalError("journal record too large")
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as error:
                raise JournalError("malformed journal JSON") from error
            if not isinstance(record, dict):
                raise JournalError("journal record must be an object")
            _validate(record, expected)
            expected += 1
            if record["seq"] > after_seq:
                records.append(record)
    return records


def append_event(
    task_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    conversation_id: str | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    source: str = "runner",
    root: Path | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    """Append one validated event, allocating the next contiguous seq."""
    path = journal_path(task_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        existing = read_records(task_id, root=root)
        record = {
            "version": 1,
            "type": event_type,
            "conversation_id": conversation_id or task_id,
            "seq": (existing[-1]["seq"] if existing else 0) + 1,
            "run_id": run_id,
            "step_id": step_id,
            "ts": ts or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": source,
            "payload": payload,
        }
        _validate(record, record["seq"])
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        return record


def iter_records(
    task_id: str, *, after_seq: int = 0, root: Path | None = None
) -> Iterator[dict[str, Any]]:
    yield from read_records(task_id, after_seq=after_seq, root=root)


def wait_for_records(
    task_id: str,
    *,
    after_seq: int,
    timeout: float = 15.0,
    interval: float = 0.2,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Blocking tail for one SSE poll; returns immediately when records exist."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        records = read_records(task_id, after_seq=after_seq, root=root)
        if records or time.monotonic() >= deadline:
            return records
        time.sleep(interval)
