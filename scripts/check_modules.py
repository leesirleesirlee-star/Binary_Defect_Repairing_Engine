#!/usr/bin/env python3
"""Check that changed files match the module registry and the PR label.

Usage:
    python scripts/check_modules.py --base origin/main
    python scripts/check_modules.py --base origin/main --labels "module:repair,type:feat"
    python scripts/check_modules.py --files app/main.py pipeline/repair/patch.py

Exit codes:
    0  every changed file belongs to a module and the label matches (if checked)
    1  an ownership, scope or label error
    2  modules.json itself is invalid
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.module_registry import (  # noqa: E402
    changed_files,
    is_ignored,
    load_registry,
    match_path,
    normalize_path,
    validate_registry,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="git ref to diff against (default: origin/main)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="explicit file list; skips git diff (used by tests)",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="comma-separated PR labels; exactly one module:<id> label is required",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="path to modules.json (default: repository root)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="repository root for git operations and the default registry",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a machine-readable report instead of a table",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else ROOT
    registry_path = Path(args.registry).resolve() if args.registry else root / "modules.json"
    registry = load_registry(registry_path)

    structural_errors = validate_registry(registry)
    if structural_errors:
        for error in structural_errors:
            print(f"invalid modules.json: {error}", file=sys.stderr)
        return 2

    if args.files is None:
        try:
            files = changed_files(args.base, root)
        except RuntimeError as exc:
            print(f"git diff failed: {exc}", file=sys.stderr)
            return 1
    else:
        files = list(args.files)
    files = [normalize_path(path) for path in files if not is_ignored(path, registry)]

    if not files:
        print("no changed files to check")
        return 0

    errors: list[str] = []
    rows: list[dict[str, str | None]] = []
    touched: set[str] = set()

    for path in files:
        module = match_path(path, registry)
        if module is None:
            rows.append({"path": path, "module": None, "owner": None})
            errors.append(f"unowned: {path} (add it to a module in modules.json)")
            continue
        rows.append({"path": path, "module": module.id, "owner": module.owner})
        touched.add(module.id)

    declared: str | None = None
    if args.labels is not None:
        prefix = registry.module_label_prefix
        module_labels = [
            label.strip()
            for label in args.labels.split(",")
            if label.strip().startswith(prefix)
        ]
        if len(module_labels) != 1:
            errors.append(
                f"exactly one {prefix}<id> label is required; found {module_labels or 'none'}"
            )
        else:
            declared = module_labels[0][len(prefix) :]
            known = {module.id for module in registry.modules}
            if declared != "integration" and declared not in known:
                errors.append(f"unknown module label: {module_labels[0]}")
            elif declared != "integration":
                for path, module in ((row["path"], row["module"]) for row in rows):
                    if module is not None and module != declared:
                        errors.append(f"outside module {declared}: {path} -> {module}")
                if declared not in touched:
                    errors.append(
                        f"declared module {declared} but no changed file belongs to it"
                    )

    if args.json:
        print(
            json.dumps(
                {
                    "base": args.base,
                    "declared_module": declared,
                    "touched_modules": sorted(touched),
                    "files": rows,
                    "errors": errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        width = max(len(row["path"]) for row in rows)
        print(f"{'file'.ljust(width)}  module / owner")
        print(f"{'-' * width}  --------------")
        for row in rows:
            if row["module"] is None:
                print(f"{row['path'].ljust(width)}  UNOWNED")
            else:
                print(f"{row['path'].ljust(width)}  {row['module']} / {row['owner']}")
        print()
        print(f"touched modules: {', '.join(sorted(touched)) or 'none'}")
        if declared:
            print(f"declared module: {declared}")
        if errors:
            print()
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
        else:
            print("OK: every changed file matches the declared module")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
