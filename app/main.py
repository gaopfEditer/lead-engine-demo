from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db.session import init_db
from app.settings import settings
from app.web.routes import router

app = FastAPI(title="Contractor Lead Engine (California)")
app.include_router(router)

static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def on_startup() -> None:
    if not settings.demo_read_only:
        init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
