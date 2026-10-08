from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Company, Suppression
from app.services.normalize import extract_domain


def load_suppressions(db: Session, path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    today = dt.date.today().isoformat()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kind = (row.get("kind") or row.get("type") or "").strip().lower()
            value = (row.get("value") or "").strip().lower()
            if not kind or not value:
                continue
            exists = (
                db.query(Suppression)
                .filter(Suppression.kind == kind, Suppression.value == value)
                .first()
            )
            if exists:
                continue
            db.add(
                Suppression(
                    kind=kind,
                    value=value,
                    reason=row.get("reason"),
                    sourced_at=row.get("sourced_at") or today,
                )
            )
            count += 1
    db.commit()
    return count


def apply_suppressions(db: Session) -> int:
    suppressions = db.query(Suppression).all()
    if not suppressions:
        return 0
    by_kind: dict[str, set[str]] = {}
    for s in suppressions:
        by_kind.setdefault(s.kind, set()).add(s.value.lower())

    hit = 0
    for company in db.query(Company).all():
        reasons: list[str] = []
        dom = (company.domain or extract_domain(company.website_url) or "").lower()
        if dom and dom in by_kind.get("domain", set()):
            reasons.append("suppression:domain")
        if company.phone_e164 and company.phone_e164.lower() in by_kind.get("phone", set()):
            reasons.append("suppression:phone")
        addr = " ".join(
            filter(
                None,
                [
                    (company.address or "").lower(),
                    (company.city or "").lower(),
                    (company.zip_code or "").lower(),
                ],
            )
        )
        if addr and addr in by_kind.get("address", set()):
            reasons.append("suppression:address")
        for contact in company.contacts:
            if contact.value.lower() in by_kind.get("email", set()):
                reasons.append("suppression:email")
        if reasons:
            company.suppressed = True
            company.suppression_reason = ";".join(reasons)
            hit += 1
    db.commit()
    return hit
