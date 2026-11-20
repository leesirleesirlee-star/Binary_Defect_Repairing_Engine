"""Tests for the module registry and the CI scope check."""

from __future__ import annotations

import pytest

from scripts.check_modules import main
from scripts.module_registry import is_ignored, load_registry, match_path, validate_registry

REGISTRY = load_registry()


def test_registry_is_structurally_valid() -> None:
    assert validate_registry(REGISTRY) == []


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("app/main.py", "gui"),
        ("app/templates/base.html", "gui"),
        ("tests/app/test_render.py", "gui"),
        ("pipeline/analyze/disasm.py", "analysis"),
        ("pipeline/ai/client.py", "ai"),
        ("prompts/fix_plan.txt", "ai"),
        ("pipeline/audit/run.py", "audit"),
        ("docs/audit/report.md", "audit"),
        ("pipeline/repair/patch.py", "repair"),
        ("pipeline/verify/verdict.py", "verify"),
        ("tests/verify/test_verdict.py", "verify"),
        ("fixtures/stack-overflow-01/vuln.elf", "fixture"),
        ("guest/run_cases.py", "guest"),
        ("schemas/ContractV1.json", "contract"),
        ("docs/interfaces/README.md", "contract"),
        ("docs/adr/0001-scope.md", "contract"),
        ("tests/contract/test_schema.py", "contract"),
        ("docs/plan/00-mvp2-roadmap.md", "infra"),
        ("README.md", "infra"),
        ("scripts/check_modules.py", "infra"),
        ("pipeline/README.md", "infra"),
    ],
)
def test_match_path(path: str, expected: str) -> None:
    module = match_path(path, REGISTRY)
    assert module is not None, path
    assert module.id == expected, path


def test_unknown_path_is_unowned() -> None:
    assert match_path("src/foo.py", REGISTRY) is None


def test_ignored_runtime_path() -> None:
    assert is_ignored("var/jobs/x.json", REGISTRY)
    assert is_ignored("__pycache__/x.pyc", REGISTRY)
    assert not is_ignored("app/main.py", REGISTRY)


def test_cli_accepts_declared_module(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--files", "app/main.py", "--labels", "module:gui"])
    assert code == 0, capsys.readouterr()
    assert "gui" in capsys.readouterr().out


def test_cli_rejects_file_outside_declared_module(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(
        [
            "--files",
            "app/main.py",
            "pipeline/repair/patch.py",
            "--labels",
            "module:gui",
        ]
    )
    assert code == 1
    assert "outside module gui" in capsys.readouterr().err


def test_cli_rejects_missing_label(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--files", "app/main.py", "--labels", ""])
    assert code == 1
    assert "exactly one module:" in capsys.readouterr().err


def test_cli_rejects_unowned_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--files", "src/foo.py"])
    assert code == 1
    assert "unowned: src/foo.py" in capsys.readouterr().err


def test_cli_allows_integration_cross_module(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "--files",
            "app/main.py",
            "pipeline/repair/patch.py",
            "--labels",
            "module:integration",
        ]
    )
    assert code == 0
    assert "declared module: integration" in capsys.readouterr().out
