from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.db.models import SyncLog
from app.services.export import exportable_companies
from app.settings import settings


def push_hubspot(db: Session) -> str:
    leads = exportable_companies(db)
    now = dt.datetime.utcnow().isoformat() + "Z"
    if not settings.hubspot_token:
        msg = f"Dry-run: would upsert {len(leads)} companies (set HUBSPOT_TOKEN to enable)."
        status = "dry_run"
    else:
        msg = f"HubSpot adapter placeholder — configure Private App token to push {len(leads)} records."
        status = "skipped"
    db.add(SyncLog(destination="hubspot", status=status, detail=msg, created_at=now))
    db.commit()
    return msg
