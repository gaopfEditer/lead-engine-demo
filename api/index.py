"""Vercel serverless entry — read-only demo using prebuilt SQLite snapshot."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Vercel provides /tmp for writable storage; copy bundled snapshot on cold start.
SNAPSHOT = Path(__file__).resolve().parents[1] / "demo_snapshot" / "lead_engine.db"
TARGET = Path("/tmp/lead_engine.db")

if SNAPSHOT.exists() and not TARGET.exists():
    shutil.copy(SNAPSHOT, TARGET)

os.environ.setdefault("DATABASE_URL", f"sqlite:///{TARGET}")
os.environ.setdefault("DEMO_READ_ONLY", "true")
os.environ.setdefault("PUBLIC_DEMO", "true")

from app.main import app as fastapi_app  # noqa: E402

app = fastapi_app
