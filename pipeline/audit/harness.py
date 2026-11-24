"""Run the three-attempt AI audit and keep every output (issue #9).

Every run stays in the table; nothing is retried or dropped. Token usage is
recorded per run so the report can carry it.
"""

from __future__ import annotations

from pipeline.ai.provider import run_plan

DEFAULT_RUNS = 3


def run_audit(
    contract: dict,
    view: dict,
    poc: dict,
    runs: int = DEFAULT_RUNS,
    api_key: str | None = None,
    model: str | None = None,
    contract_sha256: str | None = None,
    fixture_id: str | None = None,
    base_url: str | None = None,
) -> list[dict]:
    """Return one record per attempt (plan, model, usage, raw text and any error).

    A provider exception is recorded as a failed attempt; the audit never aborts
    because of one bad call, and nothing is retried.
    """
    records: list[dict] = []
    for index in range(1, runs + 1):
        print(f"run {index}/{runs}: calling model (can take 1-2 minutes)...", flush=True)
        try:
            rec = run_plan(
                contract,
                view,
                poc,
                api_key=api_key,
                model=model,
                contract_sha256=contract_sha256,
                fixture_id=fixture_id,
                base_url=base_url,
            )
        except Exception as error:  # noqa: BLE001 - a failed run is still a run
            records.append(
                {
                    "run_index": index,
                    "schema_valid": False,
                    "plan_sha256": None,
                    "plan": None,
                    "model": None,
                    "usage": None,
                    "prompt_sha256": None,
                    "raw": None,
                    "error": f"provider failed: {error.__class__.__name__}",
                }
            )
            continue
        records.append(
            {
                "run_index": index,
                "schema_valid": rec["schema_valid"],
                "plan_sha256": rec.get("response_sha256"),
                "plan": rec.get("plan"),
                "model": rec.get("model"),
                "usage": rec.get("usage"),
                "prompt_sha256": rec.get("prompt_sha256"),
                "raw": rec.get("raw"),
                "error": rec.get("error"),
            }
        )
    return records
