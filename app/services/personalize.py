from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.db.models import Company, Draft, Fact
from app.services.verify import exportable_status

BANNED = re.compile(r"\b(save|discount|guarantee|\$\d+|free audit)\b", re.I)
MAX_LEN = 220


def pick_fact(facts: list[Fact]) -> Fact | None:
    priority = ("hiring", "tech_stack", "team_member", "license_tenure")
    for kind in priority:
        for f in facts:
            if f.kind == kind:
                return f
    return facts[0] if facts else None


def draft_first_line(company: Company, fact: Fact) -> str:
    if fact.kind == "hiring":
        return f"Noticed {fact.value} on your careers page — reaching out while you're scaling the team."
    if fact.kind == "tech_stack":
        return f"Saw you're already on {fact.value} — thought a quick note on workflow add-ons might be useful."
    if fact.kind == "license_tenure":
        return f"CSLB shows you've held an active license for {fact.value} — impressive tenure in the trades."
    if fact.kind == "team_member":
        return f"Your team page highlights {fact.value} — wanted to connect about local contractor ops."
    snippet = fact.snippet[:80].strip()
    return f"Noticed on your site: {snippet} — thought it was worth a quick introduction."


def personalize_company(db: Session, company: Company) -> Draft | None:
    db.query(Draft).filter(Draft.company_id == company.id).delete()
    if not any(exportable_status(c.status, c.is_guessed) for c in company.contacts):
        return None
    fact = pick_fact(list(company.facts))
    if not fact:
        return None
    line = draft_first_line(company, fact)
    if BANNED.search(line):
        return None
    line = line[:MAX_LEN]
    draft = Draft(
        company_id=company.id,
        first_line=line,
        snippet=fact.snippet[:160],
        fact_id=fact.id,
        status="pending",
    )
    db.add(draft)
    return draft


def personalize_all(db: Session) -> int:
    n = 0
    for company in db.query(Company).all():
        if personalize_company(db, company):
            n += 1
    db.commit()
    return n
