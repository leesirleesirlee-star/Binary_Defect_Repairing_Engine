"""The GUI data layer must stay independent of the pipeline and the network."""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

FORBIDDEN = (
    "pipeline.verify",
    "pipeline.repair",
    "pipeline.ai",
    "app.backend",
    "requests",
    "httpx",
    "urllib.request",
    "http.client",
)


def test_gui_data_layer_has_no_pipeline_or_network_imports() -> None:
    sources = sorted(APP.glob("*.py"))
    assert sources, "app package has no Python modules"
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            assert forbidden not in text, f"{source.name} imports/mentions {forbidden}"
