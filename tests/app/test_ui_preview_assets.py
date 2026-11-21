"""Keep both standalone preview pages portable after asset moves."""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

UI_ROOT = Path(__file__).resolve().parents[2] / "app" / "static" / "ui"
IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\()['"]([^'"]+)['"]""")


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        key = {"link": "href", "script": "src"}.get(tag)
        if key and attributes.get(key):
            self.paths.append(attributes[key])


class PreviewAssetsTest(unittest.TestCase):
    def assert_local_file(self, origin, path):
        # Asset URLs may carry a cache-busting query string (e.g. ?v=...).
        raw = urlsplit(path).path
        if raw.startswith("/ui/"):
            target = (UI_ROOT / raw[4:]).resolve()
        else:
            target = (origin / raw).resolve()
        self.assertTrue(target.is_relative_to(UI_ROOT), path)
        self.assertTrue(target.is_file(), path)

    def test_entry_pages_reference_local_assets(self):
        for page in ("index.html", "chat/index.html", "welcome/index.html"):
            with self.subTest(page=page):
                assets = PageAssets()
                assets.feed((UI_ROOT / page).read_text(encoding="utf-8"))
                self.assertTrue(any(urlsplit(path).path.endswith(".mjs") for path in assets.paths))
                for path in assets.paths:
                    self.assert_local_file(UI_ROOT, path)

    def test_module_imports_resolve_after_reorganization(self):
        for module in UI_ROOT.rglob("*.mjs"):
            for path in IMPORT.findall(module.read_text(encoding="utf-8")):
                with self.subTest(module=module.name, path=path):
                    self.assert_local_file(module.parent, path)

    def test_both_theme_icon_assets_are_present(self):
        for theme in ("light", "dark"):
            self.assert_local_file(UI_ROOT, f"assets/mark-{theme}.svg")

    def test_welcome_assets_are_present(self):
        for path in ("welcome/index.html", "welcome/welcome.css", "welcome/welcome.mjs"):
            self.assert_local_file(UI_ROOT, path)

    def test_archive_assets_are_present(self):
        for path in ("workbench.html", "workbench/workbench.css", "workbench/workbench.mjs"):
            self.assert_local_file(UI_ROOT, path)
    def test_s2_guided_intake_assets_are_present(self):
        for path in ("chat/guided.css", "chat/guided-intake.mjs"):
            self.assert_local_file(UI_ROOT, path)
        page = (UI_ROOT / "chat/index.html").read_text(encoding="utf-8")
        self.assertNotIn('src="chat/guided-intake.mjs', page)

    def test_s3_event_console_assets_are_present(self):
        for path in ("chat/events.css", "chat/event-console.mjs"):
            self.assert_local_file(UI_ROOT, path)
        page = (UI_ROOT / "chat/index.html").read_text(encoding="utf-8")
        self.assertIn("events.css", page)

    def test_route_activity_assets_are_present(self):
        for path in ("chat/route-activity.css", "chat/route-activity.mjs"):
            self.assert_local_file(UI_ROOT, path)
        page = (UI_ROOT / "chat/index.html").read_text(encoding="utf-8")
        source = (UI_ROOT / "chat/route-activity.mjs").read_text(encoding="utf-8")
        self.assertIn("route-activity.mjs", page)
        self.assertIn("Route A", source)
        self.assertNotIn("stack-overflow", source)
        self.assertNotIn("ContractV1", source)

    def test_archive_page_does_not_mount_task_bridge(self):
        for path in ("workbench/archive-bridge.css", "workbench/archive-bridge.mjs"):
            self.assertFalse((UI_ROOT / path).exists())
        page = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("archive-bridge.css", page)
        self.assertNotIn("archive-bridge.mjs", page)



