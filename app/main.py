"""Static shell for the M2 conversation repair console.

This is the S1 server slice: it serves the copied v1.2.2 UI unchanged and does
not contain any verdict, scoring or pipeline logic. The functional API/SSE
layers arrive in later plan stages.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import SESSION_TOKEN, router as api_router
from app.fixture import snapshot

BASE_DIR = Path(__file__).resolve().parent
UI_ROOT = BASE_DIR / "static" / "ui"
# Reference v1.2.2 GUI, started beside this console by scripts/start-legacy-gui.sh.
LEGACY_URL = os.environ.get("BINARYREPAIR_LEGACY_URL", "http://127.0.0.1:8125").rstrip("/")


def _legacy_reachable() -> bool:
    """Best-effort probe so /legacy can explain how to start the reference app."""
    parts = urlsplit(LEGACY_URL)
    try:
        with socket.create_connection((parts.hostname or "127.0.0.1", parts.port or 80), timeout=0.4):
            return True
    except OSError:
        return False


_LEGACY_OFFLINE = """<!doctype html>
<html lang="zh-Hans"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>旧版界面未启动 · BinaryRepair</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d1020;color:#eef0ff;
    font-family:system-ui,-apple-system,"PingFang SC",sans-serif}
  .card{max-width:640px;padding:32px 36px;border:1px solid rgba(255,255,255,.14);border-radius:20px;
    background:rgba(24,27,48,.92);box-shadow:0 24px 60px rgba(0,0,0,.45)}
  h1{margin:0 0 12px;font-size:22px;font-weight:680}
  p{line-height:1.7;color:#b9bfe0;margin:8px 0}
  code{background:rgba(255,255,255,.08);padding:2px 7px;border-radius:6px;
    font-family:ui-monospace,Menlo,monospace}
  a{color:#80dfff}
</style></head>
<body><div class="card">
  <h1>旧版界面未启动</h1>
  <p>新版控制台仍在运行。旧版 v1.2.2 GUI 需要在本机 <code>8125</code> 端口启动，启动后两个界面可随时往返切换。</p>
  <p>在新版仓库目录执行：<br><code>./scripts/start-legacy-gui.sh</code></p>
  <p>也可以直接访问 <code>http://127.0.0.1:8125/</code>（令牌与新版共用）。返回 <a href="/welcome">新版界面</a>。</p>
</div></body></html>"""

app = FastAPI(title="BinaryRepair conversation console")
app.include_router(api_router)
app.mount("/ui", StaticFiles(directory=UI_ROOT, html=True), name="ui")


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/welcome", include_in_schema=False)
def welcome() -> FileResponse:
    return FileResponse(UI_ROOT / "welcome" / "index.html")


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse("/welcome", status_code=303)


@app.get("/api/fixture")
def fixture_snapshot() -> dict:
    """Read-only S2 data: frozen fixture, contract and corpus (no verdict)."""
    return snapshot()


@app.get("/legacy", include_in_schema=False)
def legacy() -> Response:
    """Open the reference v1.2.2 GUI that runs beside this console.

    Both applications share the same session token (the launcher passes this
    console's token to the legacy app), so the shared ``br_session`` cookie keeps
    working across the switch in either direction.
    """
    if not _legacy_reachable():
        return HTMLResponse(_LEGACY_OFFLINE, status_code=503)
    token = os.environ.get("BINARYREPAIR_LEGACY_TOKEN") or SESSION_TOKEN
    return RedirectResponse(f"{LEGACY_URL}/?token={quote(token, safe='')}", status_code=303)
