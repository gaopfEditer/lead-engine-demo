from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Company, Fact, PipelineRun
from app.services.contacts import discover_contacts, resolve_owner
from app.services.dedupe import build_merge_clusters
from app.services.enrich import _looks_like_team_member_name, enrich_company
from app.services.export import export_sample_bundle
from app.services.ingest import ingest_cslb_sample
from app.services.normalize import extract_domain
from app.services.personalize import personalize_all
from app.services.score import load_icp, score_all
from app.services.suppress import apply_suppressions, load_suppressions
from app.services.privacy import (
    mask_person_name,
    mask_sole_proprietor_business_name,
    should_mask_business_name,
)
from app.settings import settings


def _ensure_license_facts(db: Session) -> None:
    today = dt.date.today().isoformat()
    for company in db.query(Company).all():
        if not company.years_in_business:
            continue
        exists = any(f.kind == "license_tenure" for f in company.facts)
        if exists:
            continue
        val = f"{company.years_in_business} years"
        db.add(
            Fact(
                company_id=company.id,
                kind="license_tenure",
                value=val,
                evidence_url=company.source_url,
                snippet=f"Issue date {company.issue_date} ({val})",
                observed_at=today,
            )
        )
    db.commit()


def _assign_domains(db: Session) -> None:
    for company in db.query(Company).all():
        if company.website_url and not company.domain:
            company.domain = extract_domain(company.website_url)


def compute_funnel(db: Session) -> dict:
    companies = db.query(Company).all()
    total = len(companies)
    after_dedupe = sum(1 for c in companies if c.is_primary_in_cluster)
    after_hard = sum(1 for c in companies if not c.excluded_reason and c.is_primary_in_cluster)
    with_site = sum(1 for c in companies if c.website_url and not c.excluded_reason and c.is_primary_in_cluster)
    with_owner = sum(
        1
        for c in companies
        if c.owner_status == "verified" and not c.excluded_reason and c.is_primary_in_cluster
    )
    email_ok = sum(
        1
        for c in companies
        if any(ct.status == "ok" and not ct.is_guessed for ct in c.contacts)
        and not c.excluded_reason
        and c.is_primary_in_cluster
    )
    hot_warm = sum(
        1
        for c in companies
        if c.scores and c.scores[-1].tier in ("Hot", "Warm") and not c.excluded_reason and c.is_primary_in_cluster
    )
    exclude_counts = Counter(c.excluded_reason for c in companies if c.excluded_reason)
    return {
        "raw": total,
        "after_dedupe_primary": after_dedupe,
        "after_hard_exclude": after_hard,
        "with_website": with_site,
        "owner_verified": with_owner,
        "email_ok": email_ok,
        "hot_or_warm": hot_warm,
        "exclude_reasons": dict(exclude_counts.most_common(10)),
    }


def _drop_invalid_team_facts(db: Session) -> None:
    for fact in db.query(Fact).filter(Fact.kind == "team_member").all():
        if not _looks_like_team_member_name(fact.value):
            db.delete(fact)
    db.commit()


def _persist_public_demo_masks(db: Session) -> None:
    """Store masked personnel in DB for committed Vercel snapshots."""
    if not settings.public_demo:
        return
    for company in db.query(Company).all():
        lic = company.license_number or ""
        raw_business = company.business_name or ""
        if should_mask_business_name(company):
            company.business_name = mask_sole_proprietor_business_name(raw_business, license_number=lic)
        if company.mock_site_slug:
            slug = company.mock_site_slug
            company.website_url = f"https://{slug}.demo.local/"
            company.domain = f"{slug}.demo.local"
        if company.owner_name:
            company.owner_name = mask_person_name(company.owner_name, license_number=lic)
        for person in company.people:
            person.name = mask_person_name(person.name, license_number=lic)
        for fact in company.facts:
            if fact.kind == "team_member":
                if not _looks_like_team_member_name(fact.value):
                    db.delete(fact)
                    continue
                fact.value = mask_person_name(fact.value, license_number=lic)
                fact.snippet = mask_person_name(fact.snippet, license_number=lic)
    db.commit()


def run_pipeline(db: Session, *, reset: bool = True) -> PipelineRun:
    if reset:
        from app.db import models

        for model in (
            models.Draft,
            models.Score,
            models.Signal,
            models.Fact,
            models.Contact,
            models.Person,
            models.MergeCluster,
            models.Company,
            models.PipelineRun,
            models.SyncLog,
        ):
            db.query(model).delete()
        db.commit()

    started = dt.datetime.utcnow().isoformat() + "Z"
    run = PipelineRun(started_at=started, status="running", funnel_json={}, stats_json={})
    db.add(run)
    db.commit()

    stats: dict = {}
    ingest_cslb_sample(db)
    load_suppressions(db, Path(__file__).resolve().parents[2] / "data" / "suppressions.csv")
    _assign_domains(db)
    build_merge_clusters(db)
    db.commit()

    for company in db.query(Company).filter(Company.is_primary_in_cluster.is_(True)).all():
        enrich_company(db, company)
    db.commit()

    _ensure_license_facts(db)

    for company in db.query(Company).filter(Company.is_primary_in_cluster.is_(True)).all():
        resolve_owner(db, company)
        discover_contacts(db, company)
    db.commit()

    apply_suppressions(db)
    score_all(db)
    _drop_invalid_team_facts(db)
    personalize_all(db)
    _persist_public_demo_masks(db)

    out_dir = Path(__file__).resolve().parents[2] / "data" / "exports"
    csv_path, report_path = export_sample_bundle(db, out_dir)
    stats["sample_csv"] = str(csv_path)
    stats["quality_report"] = str(report_path)

    funnel = compute_funnel(db)
    run.funnel_json = funnel
    run.stats_json = stats
    run.finished_at = dt.datetime.utcnow().isoformat() + "Z"
    run.status = "completed"
    db.commit()
    return run
