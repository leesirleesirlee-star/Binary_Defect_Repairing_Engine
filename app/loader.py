"""Read-only loader for persisted JSON artifacts.

The GUI never queries the pipeline.  A screen is handed a path to a persisted
JSON artifact and this module returns the decoded object exactly as stored.

Security posture:
- paths are resolved below one repository data root;
- absolute paths and ``..`` segments that escape the root are rejected;
- symlinks that resolve outside the root are rejected;
- only regular ``.json`` files are read;
- the top-level value must be a JSON object because the GUI renders dictionaries.

The loader deliberately has no validation, verdict or success logic.  Schema
validation is the contract module's job.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8 * 1024 * 1024


class LoaderError(ValueError):
    """Base class for persisted-artifact read failures."""


class ArtifactMissing(LoaderError):
    """The requested artifact does not exist (render it as missing, not success)."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"artifact missing: {path}")


class ArtifactUnsafe(LoaderError):
    """The requested path is outside the allowed data root or is not a JSON file."""


class ArtifactInvalid(LoaderError):
    """The artifact exists but is not a JSON object."""


def _data_root(root: str | Path | None) -> Path:
    candidate = Path(root) if root is not None else DEFAULT_ROOT
    try:
        return candidate.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ArtifactUnsafe(f"data root is not readable: {candidate}") from exc


def load(path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Load one persisted JSON object below *root*.

    ``path`` may be relative to ``root`` or absolute, but the resolved path must
    stay inside ``root``.  Missing files raise :class:`ArtifactMissing` so the
    presentation layer can show ``missing`` rather than infer success.
    """
    if not isinstance(path, (str, Path)):
        raise ArtifactUnsafe("artifact path must be a string or Path")
    raw = str(path).strip()
    if not raw:
        raise ArtifactUnsafe("artifact path is empty")
    if "\x00" in raw:
        raise ArtifactUnsafe("artifact path contains a NUL byte")

    base = _data_root(root)
    requested = Path(raw).expanduser()
    candidate = requested if requested.is_absolute() else base / requested
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise ArtifactUnsafe(f"artifact path cannot be resolved: {raw}") from exc

    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ArtifactUnsafe(f"artifact path escapes the data root: {raw}") from exc

    if resolved.suffix.lower() != ".json":
        raise ArtifactUnsafe(f"artifact is not a JSON file: {raw}")
    if not resolved.exists():
        raise ArtifactMissing(raw)
    if not resolved.is_file():
        raise ArtifactUnsafe(f"artifact is not a regular file: {raw}")

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise ArtifactUnsafe(f"artifact is not readable: {raw}") from exc
    if size > MAX_BYTES:
        raise ArtifactInvalid(f"artifact exceeds the {MAX_BYTES}-byte limit: {raw}")

    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ArtifactInvalid(f"artifact is not UTF-8: {raw}") from exc
    except OSError as exc:
        raise ArtifactMissing(raw) from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactInvalid(f"artifact is not valid JSON: {raw}") from exc
    if not isinstance(payload, dict):
        raise ArtifactInvalid(f"artifact top level must be a JSON object: {raw}")
    return payload
