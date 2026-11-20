"""Module registry helpers for the MVP2 repository.

The registry is ``modules.json`` at the repository root. It is the single source
of truth for module ownership, write scope, dependencies and gates. The CI scope
check and the tests both use this module.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "modules.json"
VALID_GATES = {"G0", "G1", "G2", "G3", "G4"}


@dataclass(frozen=True)
class Module:
    """One module: a write scope with one owner and one public interface."""

    id: str
    title: str
    seat: str
    owner: str
    paths: tuple[str, ...]
    may_depend_on: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    interfaces: tuple[str, ...]
    gate: str
    notes: str


@dataclass(frozen=True)
class Registry:
    """The parsed ``modules.json`` plus its global settings."""

    modules: tuple[Module, ...]
    seats: dict[str, str]
    ignored_prefixes: tuple[str, ...]
    module_label_prefix: str
    integration_label: str


def load_registry(path: Path | None = None) -> Registry:
    """Load and parse the module registry."""

    raw = json.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))
    modules = tuple(
        Module(
            id=item["id"],
            title=item["title"],
            seat=item["seat"],
            owner=item["owner"],
            paths=tuple(item["paths"]),
            may_depend_on=tuple(item.get("may_depend_on", ())),
            forbidden_paths=tuple(item.get("forbidden_paths", ())),
            interfaces=tuple(item.get("interfaces", ())),
            gate=item["gate"],
            notes=item.get("notes", ""),
        )
        for item in raw["modules"]
    )
    return Registry(
        modules=modules,
        seats=dict(raw["seats"]),
        ignored_prefixes=tuple(raw.get("ignored_prefixes", ())),
        module_label_prefix=raw.get("module_label_prefix", "module:"),
        integration_label=raw.get("integration_label", "module:integration"),
    )


def normalize_path(path: str) -> str:
    """Normalize a repository-relative path to forward slashes."""

    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def is_ignored(path: str, registry: Registry) -> bool:
    """Return True for runtime or tooling paths that are not tracked."""

    normalized = normalize_path(path)
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in registry.ignored_prefixes
    )


def match_path(path: str, registry: Registry) -> Module | None:
    """Return the module that owns ``path``, or None if it is unowned.

    Exact file rules win over prefix rules; among prefixes, the longest one wins.
    A tie between two different modules is a registry bug and raises ValueError.
    """

    normalized = normalize_path(path)
    for module in registry.modules:
        for rule in module.paths:
            if not rule.endswith("/") and normalized == normalize_path(rule):
                return module

    best_length = -1
    best: Module | None = None
    for module in registry.modules:
        for rule in module.paths:
            if not rule.endswith("/"):
                continue
            prefix = normalize_path(rule)
            if not normalized.startswith(prefix):
                continue
            if len(prefix) > best_length:
                best_length = len(prefix)
                best = module
            elif len(prefix) == best_length and best is not None and best.id != module.id:
                raise ValueError(
                    f"ambiguous path {normalized!r}: {best.id} and {module.id} "
                    f"both claim prefix {prefix!r}"
                )
    return best


def classify(paths: list[str], registry: Registry) -> list[tuple[str, Module | None]]:
    """Classify each path, preserving input order."""

    return [(normalize_path(path), match_path(path, registry)) for path in paths]


def validate_registry(registry: Registry) -> list[str]:
    """Return a list of structural errors; empty means the registry is valid."""

    errors: list[str] = []
    ids = [module.id for module in registry.modules]
    if len(ids) != len(set(ids)):
        errors.append("duplicate module id in modules.json")

    for module in registry.modules:
        if module.seat not in registry.seats:
            errors.append(f"{module.id}: unknown seat {module.seat!r}")
        elif registry.seats[module.seat] != module.owner:
            errors.append(
                f"{module.id}: owner {module.owner!r} does not match seat "
                f"{module.seat} ({registry.seats[module.seat]!r})"
            )
        if module.gate not in VALID_GATES:
            errors.append(f"{module.id}: invalid gate {module.gate!r}")
        if not module.paths:
            errors.append(f"{module.id}: empty paths list")
        for dependency in module.may_depend_on:
            if dependency not in ids:
                errors.append(f"{module.id}: unknown dependency {dependency!r}")
            if dependency == module.id:
                errors.append(f"{module.id}: depends on itself")
        for rule in module.paths:
            if not rule.endswith("/") and "/" in rule and rule.startswith("."):
                # A dot-prefixed directory rule such as ".github/" ends with "/",
                # so this only catches suspicious exact file paths.
                errors.append(f"{module.id}: suspicious exact path {rule!r}")

    return errors


def changed_files(base: str, root: Path | None = None) -> list[str]:
    """Return files changed between ``base`` and HEAD.

    Raises RuntimeError when git fails, for example because the base ref was not
    fetched in CI.
    """

    command = ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"]
    result = subprocess.run(
        command,
        cwd=root or ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git diff failed"
        raise RuntimeError(message)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
