from __future__ import annotations

import csv
import datetime as dt
import json
from io import StringIO
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Company, Contact, MergeCluster, Score
from app.services.verify import exportable_status


def _latest_score(company: Company) -> Score | None:
    if not company.scores:
        return None
    return sorted(company.scores, key=lambda s: s.id, reverse=True)[0]


def exportable_companies(db: Session) -> list[Company]:
    out: list[Company] = []
    for company in db.query(Company).all():
        sc = _latest_score(company)
        if not sc or sc.tier == "Cold":
            continue
        if company.excluded_reason or company.suppressed:
            continue
        if not any(exportable_status(c.status, c.is_guessed) for c in company.contacts):
            continue
        if not company.is_primary_in_cluster:
            continue
        out.append(company)
    return out


def leads_to_csv_rows(db: Session, companies: list[Company]) -> list[dict]:
    rows: list[dict] = []
    for company in companies:
        sc = _latest_score(company)
        email = next(
            (c.value for c in company.contacts if exportable_status(c.status, c.is_guessed)),
            "",
        )
        draft = company.drafts[0] if company.drafts else None
        rows.append(
            {
                "license_number": company.license_number,
                "business_name": company.business_name,
                "county": company.county,
                "classifications": company.classifications,
                "owner_name": company.owner_name or "",
                "email": email,
                "phone_e164": company.phone_e164 or "",
                "website": company.website_url or "",
                "score": sc.score if sc else "",
                "tier": sc.tier if sc else "",
                "first_line": draft.first_line if draft else "",
                "source_url": company.source_url,
                "sourced_at": company.sourced_at,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def quality_report(db: Session) -> dict:
    companies = db.query(Company).all()
    contacts = db.query(Contact).all()
    status_counts: dict[str, int] = {}
    for c in contacts:
        status_counts[c.status] = status_counts.get(c.status, 0) + 1
    merge_count = db.query(MergeCluster).count()
    tiers = {"Hot": 0, "Warm": 0, "Cold": 0}
    for company in companies:
        sc = _latest_score(company)
        if sc:
            tiers[sc.tier] = tiers.get(sc.tier, 0) + 1
    exportables = exportable_companies(db)
    return {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "companies_total": len(companies),
        "merge_clusters": merge_count,
        "verification_status": status_counts,
        "tier_counts": tiers,
        "exportable_leads": len(exportables),
        "owner_verified": sum(1 for c in companies if c.owner_status == "verified"),
        "with_website": sum(1 for c in companies if c.website_url),
        "guessed_emails": sum(1 for c in contacts if c.is_guessed),
        "role_emails": sum(1 for c in contacts if c.is_role_based),
    }


def export_sample_bundle(db: Session, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    companies = exportable_companies(db)
    companies = sorted(companies, key=lambda c: _latest_score(c).score if _latest_score(c) else 0, reverse=True)[
        :50
    ]
    rows = leads_to_csv_rows(db, companies)
    csv_path = out_dir / "sample_50_leads.csv"
    report_path = out_dir / "quality_report.json"
    write_csv(csv_path, rows)
    report = quality_report(db)
    report["sample_size"] = len(rows)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return csv_path, report_path


def csv_string(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
