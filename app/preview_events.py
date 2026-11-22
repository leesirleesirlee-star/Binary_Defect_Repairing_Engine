"""Clearly labelled synthetic journal for the S3 `?preview=1` rendering path.

Preview events exercise the rendering contract only. They are never written as
real run history and never contain a success verdict or a passed verification.
"""

from __future__ import annotations

from app.journal import append_event, read_records


def ensure_preview_journal(task_id: str) -> None:
    if read_records(task_id):
        return
    base = {"conversation_id": task_id, "source": "synthetic"}
    append_event(
        task_id,
        "run_state",
        {"status": "running", "message_id": None},
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "corpus_update",
        {
            "fixture_id": "stack-overflow-01",
            "counts": {"valid": 5, "invalid": 4, "poc": 0},
            "total": 9,
            "cases_sha256": "fae5efd054358d16610987f5645eadc582ce53ac12debeb356941d6617ceec3d",
        },
        step_id="collect",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "plan_update",
        {
            "revision": 1,
            "steps": [
                {"step_id": step, "label_code": step, "status": status}
                for step, status in zip(
                    (
                        "collect",
                        "freeze",
                        "analyze",
                        "audit",
                        "decision",
                        "repair",
                        "verify",
                        "export",
                    ),
                    (
                        "completed",
                        "completed",
                        "in_progress",
                        "pending",
                        "pending",
                        "pending",
                        "pending",
                        "pending",
                    ),
                    strict=True,
                )
            ],
        },
        step_id="freeze",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "command",
        {
            "command_id": "preview-analyze",
            "phase": "started",
            "label_code": "analysis",
            "display_cwd": "evidence",
        },
        step_id="analyze",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "file_change",
        {
            "change_id": "preview-view",
            "stage": "proposed",
            "files": [
                {
                    "display_path": "disassembly-view.json",
                    "added": 1,
                    "removed": 0,
                    "diff": {"text": "preview fixture only\n", "truncated": False},
                }
            ],
        },
        step_id="analyze",
        run_id="run_preview",
        **base,
    )
    for level in ("V0", "V1", "V2", "V3", "V4"):
        append_event(
            task_id,
            "verification",
            {
                "kind": "check",
                "level": level,
                "status": "not_run",
                "obligation_id": "preview-" + level,
                "evidence_ids": [],
                "reason_code": "preview_only",
            },
            step_id="verify",
            run_id="run_preview",
            **base,
        )
    append_event(
        task_id,
        "verification",
        {
            "kind": "evaluation",
            "evaluation_id": "preview-evaluation",
            "verdict": None,
            "generated_at": "2026-11-20T15:00:00Z",
        },
        step_id="verify",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "audit_runs",
        {
            "report_sha256": "0" * 64,
            "runs": [
                {
                    "run_index": 1,
                    "schema_valid": False,
                    "score": None,
                    "critical_errors": ["invalid_json"],
                    "usable": False,
                    "notes": "synthetic preview row, never a real audit",
                },
                {
                    "run_index": 2,
                    "schema_valid": True,
                    "score": None,
                    "critical_errors": [],
                    "usable": False,
                    "notes": "synthetic preview row, no scores reported",
                },
                {
                    "run_index": 3,
                    "schema_valid": True,
                    "score": None,
                    "critical_errors": [],
                    "usable": False,
                    "notes": "synthetic preview row, no scores reported",
                },
            ],
        },
        step_id="audit",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "awaiting_user",
        {
            "request_id": "preview-decision",
            "kind": "audit_decision",
            "allowed": ["proceed", "iterate", "change_scope"],
            "binding": {
                "contract_revision": 1,
                "contract_sha256": "0" * 64,
                "corpus_sha256": "0" * 64,
                "binary_sha256": "0" * 64,
            },
        },
        step_id="decision",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "file_change",
        {
            "change_id": "preview-repair",
            "stage": "proposed",
            "files": [
                {
                    "display_path": "candidate.elf",
                    "added": 0,
                    "removed": 0,
                    "diff": {
                        "text": "synthetic preview only; candidate_written: false\n",
                        "truncated": False,
                    },
                }
            ],
        },
        step_id="repair",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "error",
        {"code": "preview_only", "correlation_id": "preview", "retry": {"kind": "manual"}},
        step_id="verify",
        run_id="run_preview",
        **base,
    )
    append_event(
        task_id,
        "run_end",
        {
            "execution": "failed",
            "duration_ms": 0,
            "steps_taken": 2,
            "files_changed": 1,
            "ai": {"calls": None, "tokens": None, "cost_usd": None},
            "evaluation_id": "preview-evaluation",
        },
        step_id="verify",
        run_id="run_preview",
        **base,
    )
