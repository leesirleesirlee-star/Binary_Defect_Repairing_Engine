"""Child-only audit runner for G4.1 live mode.

The API host spawns this module as a separate process with the provider key only
in the child environment.  It uses the frozen audit harness (the same code the
G2 CLI uses) and writes the raw run records + `summary.json` required by
`docs/interfaces/live-ai-run-v1.md`.

Why this wrapper: the current `pipeline.audit` CLI does not yet accept
`--summary-out` / `--model` and does not pass `contract_sha256` into the harness
(#61).  This child therefore calls the same `pipeline.audit.harness.run_audit`
directly, without changing the pipeline.  It is a compatibility seam, not a new
audit implementation; once #61 lands the API can spawn that CLI instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument("--model", required=True)
    args = parser.parse_args(argv)

    from pipeline.analyze import build_disassembly_view
    from pipeline.audit.harness import run_audit

    contract_path = args.fixture_dir / "contract.json"
    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes.decode("utf-8"))
    contract_sha256 = hashlib.sha256(contract_bytes).hexdigest()
    view = build_disassembly_view(args.fixture_dir / "vuln.elf")
    poc = {"input": "A" * 64, "observed_output": {"signal": "SIGSEGV"}}
    def one_run(index: int) -> dict:
        result = run_audit(
            contract,
            view,
            poc,
            runs=1,
            model=args.model,
            contract_sha256=contract_sha256,
            fixture_id=contract.get("fixture_id"),
        )
        record = dict(result[0]) if result else {"schema_valid": False, "plan": None}
        record["run_index"] = index
        return record

    # The three audit attempts are independent; run them concurrently so the
    # 10-minute API timeout covers the real 1-2 minute provider calls.
    with ThreadPoolExecutor(max_workers=max(1, args.runs)) as pool:
        records = list(pool.map(one_run, range(1, args.runs + 1)))
    raw_dir = args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    for record in records:
        (raw_dir / f"run-{record.get('run_index')}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        runs.append({
            "run_index": record.get("run_index"),
            "schema_valid": bool(record.get("schema_valid")),
            "plan_sha256": record.get("plan_sha256"),
            "model": record.get("model"),
            "usage": record.get("usage") or {},
            "plan": record.get("plan"),
            "error": record.get("error"),
        })
    summary = {
        "model": args.model,
        "contract_sha256": contract_sha256,
        "runs": runs,
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
