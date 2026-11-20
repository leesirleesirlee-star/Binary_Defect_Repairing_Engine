"""Static shell for the M2 conversation repair console.

This is the S1 server slice: it serves the copied v1.2.2 UI unchanged and does
not contain any verdict, scoring or pipeline logic. The functional API/SSE
layers arrive in later plan stages.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.fixture import snapshot

BASE_DIR = Path(__file__).resolve().parent
UI_ROOT = BASE_DIR / "static" / "ui"

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
