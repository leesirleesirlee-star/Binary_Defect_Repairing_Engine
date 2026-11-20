"""CLI: run the three-attempt G2 audit against the frozen fixture.

Reads ``DEEPSEEK_API_KEY`` and ``DEEPSEEK_MODEL`` from the host process
environment. Raw responses are written under ``docs/audit/raw/`` (key never
included); a summary line is printed per run.
"""

from __future__ import annotations

import argparse
import json
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
    args = parser.parse_args(argv)

    root = args.fixture_dir
    contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
    view = build_disassembly_view(root / "vuln.elf")

    records = run_audit(contract, view, _POC, runs=args.runs)

    raw = args.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    for rec in records:
        out = raw / f"run-{rec['run_index']}.json"
        out.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        usage = rec.get("usage") or {}
        tokens = usage.get("total_tokens")
        print(
            f"run {rec['run_index']}: schema_valid={rec['schema_valid']} "
            f"model={rec['model']} total_tokens={tokens} sha256={rec['plan_sha256'][:12]}"
        )
    print(f"raw records -> {raw.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
