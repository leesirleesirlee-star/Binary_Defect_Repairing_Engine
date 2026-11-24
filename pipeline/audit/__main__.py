"""CLI: run the three-attempt G2 audit against the frozen fixture.

Reads ``DEEPSEEK_API_KEY`` and ``DEEPSEEK_MODEL`` from the host process
environment. Raw responses are written under ``docs/audit/raw/`` (key never
included); a summary line is printed per run. ``--summary-out`` writes a
machine-readable live summary; ``--model`` and ``--base-url`` pin the transport.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from pipeline.analyze import build_disassembly_view
from pipeline.audit.harness import run_audit

# Frozen PoC: 64 'A' bytes; the original is observed to die with SIGSEGV.
_POC = {"input": "A" * 64, "observed_output": {"signal": "SIGSEGV"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--raw-dir", type=Path, default=Path("docs/audit/raw"))
    parser.add_argument("--summary-out", type=Path, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args(argv)

    root = args.fixture_dir
    contract_bytes = (root / "contract.json").read_bytes()
    contract = json.loads(contract_bytes.decode("utf-8"))
    contract_sha256 = hashlib.sha256(contract_bytes).hexdigest()
    view = build_disassembly_view(root / "vuln.elf")

    records = run_audit(
        contract,
        view,
        _POC,
        runs=args.runs,
        model=args.model,
        base_url=args.base_url,
        contract_sha256=contract_sha256,
        fixture_id=contract.get("fixture_id"),
    )

    raw = args.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    for rec in records:
        out = raw / f"run-{rec['run_index']}.json"
        out.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        usage = rec.get("usage") or {}
        tokens = usage.get("total_tokens")
        sha = rec.get("plan_sha256") or "(none)"
        print(
            f"run {rec['run_index']}: schema_valid={rec['schema_valid']} "
            f"model={rec['model']} total_tokens={tokens} sha256={sha[:12]}"
        )
    print(f"raw records -> {raw.resolve()}")

    if args.summary_out is not None:
        summary = {
            "model": args.model or os.environ.get("DEEPSEEK_MODEL"),
            "prompt_sha256": records[0]["prompt_sha256"] if records else None,
            "contract_sha256": contract_sha256,
            "runs": [
                {
                    "run_index": rec["run_index"],
                    "schema_valid": rec["schema_valid"],
                    "plan_sha256": rec["plan_sha256"],
                    "plan": rec["plan"],
                    "usage": rec["usage"],
                }
                for rec in records
            ],
        }
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"summary -> {args.summary_out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
