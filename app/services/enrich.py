from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser
from sqlalchemy.orm import Session

from app.db.models import Company, Fact, Signal
from app.services.crawl import fetch_html, pick_paths
from app.settings import settings

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
FRANCHISE_RE = re.compile(r"\b(franchise|franchising|national chain|corporate location)\b", re.I)
TECH_RE = re.compile(r"\b(ServiceTitan|Housecall Pro|Jobber|Schedule Engine)\b", re.I)


def _add_fact(db: Session, company: Company, kind: str, value: str, url: str, snippet: str) -> Fact:
    fact = Fact(
        company_id=company.id,
        kind=kind,
        value=value,
        evidence_url=url,
        snippet=snippet[:500],
        observed_at=dt.date.today().isoformat(),
    )
    db.add(fact)
    db.flush()
    return fact


def enrich_company(db: Session, company: Company) -> None:
    if not company.website_url:
        company.pipeline_stage = "no_website"
        return

    base = company.website_url if company.website_url.endswith("/") else company.website_url + "/"
    homepage, err = fetch_html(base)
    if not homepage:
        company.excluded_reason = err or "fetch_failed"
        company.pipeline_stage = "fetch_failed"
        return

    pages = {base: homepage}
    for path in pick_paths(base, homepage):
        if path in pages:
            continue
        html, _ = fetch_html(path)
        if html:
            pages[path] = html

    for url, html in pages.items():
        tree = LexborHTMLParser(html)
        text = tree.text(separator=" ", strip=True)
        low_url = url.lower()

        for mail in set(EMAIL_RE.findall(html)):
            snippet = mail
            _add_fact(db, company, "email", mail.lower(), url, snippet)

        if FRANCHISE_RE.search(text):
            m = FRANCHISE_RE.search(text)
            _add_fact(db, company, "franchise", "franchise_indicator", url, m.group(0) if m else "franchise")

        if any(k in low_url for k in ("career", "job")) or "now hiring" in text.lower():
            jobs = len(re.findall(r"(technician|installer|journeyman|apprentice)", text, re.I))
            jobs = max(jobs, 1)
            _add_fact(db, company, "hiring", f"{jobs} open roles mentioned", url, text[:240])
            db.add(
                Signal(
                    company_id=company.id,
                    kind="hiring",
                    strength=min(1.0, 0.4 + jobs * 0.15),
                    detail=f"{jobs} roles",
                    evidence_url=url,
                    observed_at=dt.date.today().isoformat(),
                    decays_at=(dt.date.today() + dt.timedelta(days=45)).isoformat(),
                )
            )

        if any(k in low_url for k in ("team", "about", "staff")):
            for h in tree.css("h1,h2,h3,strong"):
                t = h.text(strip=True)
                if t and 3 < len(t) < 80:
                    _add_fact(db, company, "team_member", t, url, t)

        if TECH_RE.search(text):
            m = TECH_RE.search(text)
            _add_fact(db, company, "tech_stack", m.group(0), url, m.group(0))

        if "facebook.com" in html.lower() and "official website" not in text.lower():
            _add_fact(db, company, "social_only", "facebook_presence", url, "Facebook link detected")

    if company.years_in_business and company.years_in_business >= 10:
        db.add(
            Signal(
                company_id=company.id,
                kind="years_in_business",
                strength=min(1.0, company.years_in_business / 25),
                detail=f"{company.years_in_business} years",
                evidence_url=company.source_url,
                observed_at=dt.date.today().isoformat(),
                decays_at=None,
            )
        )

    company.pipeline_stage = "enriched"
