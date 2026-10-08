from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Company, Person
from app.services.normalize import extract_domain, normalize_phone
from app.settings import settings


def _years_since(issue: str | None) -> float | None:
    if not issue:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            d = dt.datetime.strptime(str(issue).split()[0], fmt).date()
            return round((dt.date.today() - d).days / 365.25, 1)
        except ValueError:
            continue
    return None


def load_mock_registry(path: Path | None = None) -> dict[str, dict]:
    path = path or Path(__file__).resolve().parents[2] / "data" / "mock_site_registry.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ingest_cslb_sample(db: Session, csv_path: Path | None = None) -> tuple[int, int]:
    csv_path = csv_path or settings.cslb_sample_path
    meta_path = csv_path.with_suffix(".meta.json")
    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    source_url = meta.get("source_url", "https://www.cslb.ca.gov/OnlineServices/DataPortal/")
    sourced_at = meta.get("download_date", dt.date.today().isoformat())
    synthetic = bool(meta.get("synthetic", False))
    registry = load_mock_registry()

    licenses: dict[str, dict] = {}
    personnel_by_license: dict[str, list[dict]] = {}

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rtype = (row.get("record_type") or "license").lower()
            lic = str(row.get("LicenseNumber") or "").strip()
            if not lic:
                continue
            if rtype == "personnel":
                personnel_by_license.setdefault(lic, []).append(row)
            else:
                licenses[lic] = row

    db.query(Person).delete()
    db.query(Company).delete()
    db.commit()

    company_count = 0
    people_count = 0
    for lic, row in licenses.items():
        reg = registry.get(lic, {})
        slug = reg.get("slug")
        website = reg.get("website_url")
        if slug:
            website = f"{settings.mock_sites_base_url.rstrip('/')}/sites/{slug}/"
        elif website and "127.0.0.1:8081" in website:
            website = website.replace("http://127.0.0.1:8081", settings.mock_sites_base_url.rstrip("/"))
        phone_e164, phone_type = normalize_phone(row.get("PhoneNumber"))
        domain = reg.get("domain")
        if not domain and slug:
            domain = f"{slug}.demo.local"
        elif not domain and website:
            domain = extract_domain(website)
        if domain == "127.0.0.1":
            domain = f"{slug}.demo.local" if slug else domain
        company = Company(
            license_number=lic,
            business_name=row.get("BusinessName") or f"License {lic}",
            business_type=row.get("BusinessType"),
            address=row.get("Address"),
            city=row.get("City"),
            state=row.get("State"),
            zip_code=str(row.get("ZIP Code") or ""),
            county=row.get("County"),
            phone_raw=row.get("PhoneNumber"),
            phone_e164=phone_e164,
            phone_type=phone_type,
            domain=domain,
            website_url=website,
            classifications=row.get("Classification(s)"),
            license_status=row.get("Status"),
            issue_date=str(row.get("IssueDate") or ""),
            expiration_date=str(row.get("ExpirationDate") or ""),
            years_in_business=_years_since(str(row.get("IssueDate") or "")),
            source_url=source_url,
            sourced_at=sourced_at,
            mock_site_slug=slug,
            synthetic=synthetic,
            pipeline_stage="ingested",
        )
        db.add(company)
        db.flush()
        company_count += 1

        for prow in personnel_by_license.get(lic, []):
            name = (prow.get("PersonnelName") or prow.get("Name") or "").strip()
            if not name:
                continue
            db.add(
                Person(
                    company_id=company.id,
                    name=name,
                    title=(prow.get("PersonnelTitle") or prow.get("EMP-Titl-CDE") or ""),
                    source_url=source_url,
                    sourced_at=sourced_at,
                )
            )
            people_count += 1

    db.commit()
    return company_count, people_count
