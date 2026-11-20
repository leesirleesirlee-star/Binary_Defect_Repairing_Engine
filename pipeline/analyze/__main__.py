"""CLI: emit ``disassembly.json`` and ``finding.json`` for the fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .finding import build_finding
from .view import build_disassembly_view


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--fixture-id", default="stack-overflow-01")
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    view = build_disassembly_view(args.elf)
    (out / "disassembly.json").write_text(json.dumps(view, indent=2) + "\n", encoding="utf-8")

    finding = build_finding(view, args.fixture_id)
    (out / "finding.json").write_text(json.dumps(finding, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(finding, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
