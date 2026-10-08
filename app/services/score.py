from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.db.models import Company, Fact, Score
from app.services.llm.client import chat_json, llm_available
from app.services.llm.grounding import validate_reasons
from app.services.verify import exportable_status
from app.settings import settings


def load_icp(path: Path | None = None) -> dict[str, Any]:
    path = path or settings.icp_config_path
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _tier(score: int, icp: dict[str, Any]) -> str:
    th = icp.get("thresholds", {})
    if score >= th.get("hot", 75):
        return "Hot"
    if score >= th.get("warm", 55):
        return "Warm"
    return "Cold"


def hard_exclude(company: Company, icp: dict[str, Any]) -> str | None:
    hx = icp.get("hard_excludes", {})
    if hx.get("require_website") and not company.website_url:
        return "no_website"
    if company.license_status and company.license_status.upper() in {
        s.upper() for s in hx.get("exclude_license_status", [])
    }:
        return "bad_license_status"
    min_years = hx.get("min_years_in_business")
    if min_years and (company.years_in_business or 0) < min_years:
        return "too_new"
    county_list = icp.get("counties") or []
    if county_list and company.county and company.county not in county_list:
        return "county_out_of_icp"
    if hx.get("franchise_fact") and any(f.kind == "franchise" for f in company.facts):
        return "franchise"
    for kw in hx.get("national_chain_keywords", []):
        if kw.upper() in (company.business_name or "").upper():
            return "national_chain"
    if company.suppressed:
        return "suppressed"
    if not company.is_primary_in_cluster:
        return "duplicate_non_primary"
    return None


def rule_score(company: Company, icp: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    w = icp.get("weights", {})
    score = 0
    reasons: list[dict[str, Any]] = []
    tenure_fact = next((f for f in company.facts if f.kind == "license_tenure"), None)
    if company.years_in_business and tenure_fact:
        pts = min(w.get("years_in_business", 25), int(company.years_in_business))
        score += pts
        reasons.append(
            {
                "text": f"{company.years_in_business} years in business (CSLB issue date)",
                "fact_id": tenure_fact.id,
                "snippet": tenure_fact.snippet[:120],
            }
        )
    if any(s.kind == "hiring" for s in company.signals):
        score += w.get("hiring_signal", 20)
        sig = next(s for s in company.signals if s.kind == "hiring")
        fact = next((f for f in company.facts if f.kind == "hiring"), None)
        if fact:
            reasons.append({"text": "Active hiring signal on careers page", "fact_id": fact.id, "snippet": fact.snippet[:120]})
    if any(f.kind == "team_member" for f in company.facts):
        score += w.get("team_page", 10)
        fact = next(f for f in company.facts if f.kind == "team_member")
        reasons.append({"text": "Team/About page lists staff", "fact_id": fact.id, "snippet": fact.snippet[:120]})
    if any(f.kind == "tech_stack" for f in company.facts):
        score += w.get("tech_stack", 8)
        fact = next(f for f in company.facts if f.kind == "tech_stack")
        reasons.append({"text": "Field-service software detected", "fact_id": fact.id, "snippet": fact.snippet[:120]})
    if company.owner_status == "verified":
        score += w.get("owner_verified", 15)
        team_fact = next((f for f in company.facts if f.kind == "team_member"), None)
        if team_fact:
            reasons.append(
                {
                    "text": "Owner cross-checked against CSLB personnel and website team page",
                    "fact_id": team_fact.id,
                    "snippet": team_fact.snippet[:120],
                }
            )
    if any(exportable_status(c.status, c.is_guessed) for c in company.contacts):
        score += w.get("email_ok", 12)
    return min(score, 100), reasons


def offline_llm_score(company: Company, facts: list) -> list[dict[str, Any]]:
    extra: list[dict[str, Any]] = []
    for fact in facts:
        if fact.kind == "hiring":
            extra.append({"text": "Hiring activity suggests capacity constraints", "fact_id": fact.id, "snippet": fact.snippet[:120]})
        if fact.kind == "tech_stack":
            extra.append({"text": "Existing scheduling stack may integrate with add-on services", "fact_id": fact.id, "snippet": fact.snippet[:120]})
    return extra[:2]


def score_company(db: Session, company: Company, icp: dict[str, Any]) -> Score | None:
    reason = hard_exclude(company, icp)
    if reason:
        company.excluded_reason = reason
        company.pipeline_stage = "excluded"
        return None

    base, reasons = rule_score(company, icp)
    facts = list(company.facts)
    llm_reasons: list[dict[str, Any]] = []
    if llm_available():
        payload = chat_json(
            "Return JSON {reasons:[{fact_id,text,snippet}]}. Only use provided facts.",
            str(
                [
                    {"fact_id": f.id, "kind": f.kind, "value": f.value, "snippet": f.snippet}
                    for f in facts
                ]
            ),
        )
        if payload and isinstance(payload.get("reasons"), list):
            llm_reasons = validate_reasons(payload["reasons"], facts)
    else:
        llm_reasons = offline_llm_score(company, facts)

    reasons = [r for r in reasons if r.get("fact_id") is not None]
    reasons.extend(llm_reasons)
    reasons = validate_reasons(reasons, facts)

    final_score = min(100, base + len(llm_reasons) * 3)
    tier = _tier(final_score, icp)
    sc = Score(
        company_id=company.id,
        icp_version=icp.get("version", "v1"),
        score=final_score,
        tier=tier,
        reasons_json=reasons,
        created_at=dt.date.today().isoformat(),
    )
    db.add(sc)
    company.pipeline_stage = "scored"
    return sc


def score_all(db: Session, icp: dict[str, Any] | None = None) -> int:
    icp = icp or load_icp()
    db.query(Score).delete()
    count = 0
    for company in db.query(Company).all():
        if score_company(db, company, icp):
            count += 1
    db.commit()
    return count
