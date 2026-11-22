"""S3 event-journal envelope, replay and gap tests."""
from __future__ import annotations

import json

import pytest

from app.journal import JournalError, JournalGap, append_event, journal_path, read_records


def test_append_and_replay(tmp_path) -> None:
    root = tmp_path / "events"
    first = append_event(
        "tsk_abc", "run_state", {"status": "running"}, root=root, source="synthetic")
    second = append_event(
        "tsk_abc", "thinking", {"phase": "started"}, root=root, source="synthetic")
    assert [first["seq"], second["seq"]] == [1, 2]
    assert [record["seq"] for record in read_records("tsk_abc", root=root)] == [1, 2]
    assert [record["seq"] for record in read_records("tsk_abc", after_seq=1, root=root)] == [2]


def test_sequence_gap_fails_closed(tmp_path) -> None:
    root = tmp_path / "events"
    append_event("tsk_gap", "run_state", {"status": "running"}, root=root, source="synthetic")
    path = journal_path("tsk_gap", root)
    record = json.loads(path.read_text().splitlines()[0])
    record["seq"] = 3
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(JournalGap):
        read_records("tsk_gap", root=root)


def test_invalid_envelope_rejected(tmp_path) -> None:
    root = tmp_path / "events"
    path = journal_path("tsk_bad", root)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "type": "run_state"}) + "\n", encoding="utf-8")
    with pytest.raises(JournalError):
        read_records("tsk_bad", root=root)


def test_task_id_and_source_validation(tmp_path) -> None:
    root = tmp_path / "events"
    with pytest.raises(JournalError):
        append_event("../escape", "run_state", {}, root=root, source="synthetic")
    with pytest.raises(JournalError):
        append_event("tsk_ok", "run_state", {}, root=root, source="unknown")
