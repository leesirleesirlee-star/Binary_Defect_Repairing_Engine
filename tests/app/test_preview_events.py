"""S3-S5 preview journal content: every card is synthetic and no success leaks."""
from __future__ import annotations

from app.journal import read_records
from app.preview_events import ensure_preview_journal


def test_preview_covers_plan_cards_without_success(tmp_path, monkeypatch) -> None:
    from app import journal

    monkeypatch.setattr(journal, "_root", lambda root=None: tmp_path / "events")
    task_id = "tsk_previewcards"
    ensure_preview_journal(task_id)
    records = read_records(task_id)
    types = [record["type"] for record in records]
    assert "audit_runs" in types
    assert "awaiting_user" in types
    assert "file_change" in types
    assert "run_end" in types
    audit = next(record for record in records if record["type"] == "audit_runs")
    assert len(audit["payload"]["runs"]) == 3
    decision = next(record for record in records if record["type"] == "awaiting_user")
    assert decision["payload"]["kind"] == "audit_decision"
    assert decision["payload"]["allowed"] == ["proceed", "iterate", "change_scope"]
    checks = [record for record in records
              if record["type"] == "verification" and record["payload"].get("kind") == "check"]
    assert checks and all(record["payload"]["status"] == "not_run" for record in checks)
    evaluations = [record for record in records
                   if record["type"] == "verification"
                   and record["payload"].get("kind") == "evaluation"]
    assert evaluations and all(record["payload"]["verdict"] is None for record in evaluations)
    assert records[-1]["payload"]["execution"] != "completed"
    assert all(record["source"] == "synthetic" for record in records)
