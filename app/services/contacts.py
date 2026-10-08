from __future__ import annotations

import datetime as dt
import re

from sqlalchemy.orm import Session

from app.db.models import Company, Contact, Fact, Person
from app.services.normalize import is_role_email
from app.services.verify import verify_email
from app.settings import settings

OWNER_TITLE_HINTS = ("owner", "president", "ceo", "qualifying", "rmo", "officer", "member")


def _name_tokens(name: str) -> set[str]:
    return {t.lower() for t in re.split(r"[^A-Za-z]+", name) if len(t) > 2}


def resolve_owner(db: Session, company: Company) -> None:
    cslb_people = company.people
    team_facts = [f for f in company.facts if f.kind == "team_member"]
    owner_name = None
    evidence_parts: list[str] = []

    for person in cslb_people:
        title = (person.title or "").lower()
        title_ok = any(h in title for h in OWNER_TITLE_HINTS) or title in {"q", "o", "p", "r"}
        for fact in team_facts:
            if _name_tokens(person.name) & _name_tokens(fact.value):
                if title_ok or fact.kind == "team_member":
                    owner_name = person.name
                    evidence_parts.append(f"CSLB personnel matches website team page ({person.title or 'personnel'})")
                    break
        if owner_name:
            break

    if owner_name:
        company.owner_name = owner_name
        company.owner_status = "verified"
        company.owner_evidence = "; ".join(evidence_parts)
    else:
        company.owner_name = None
        company.owner_status = "not_found"
        company.owner_evidence = None


def discover_contacts(db: Session, company: Company) -> None:
    today = dt.date.today().isoformat()
    db.query(Contact).filter(Contact.company_id == company.id).delete()

    seen: set[str] = set()
    for fact in company.facts:
        if fact.kind != "email":
            continue
        email = fact.value.lower()
        if email in seen:
            continue
        seen.add(email)
        v = verify_email(email, guessed=False)
        db.add(
            Contact(
                company_id=company.id,
                contact_type="email",
                value=email,
                status=v["status"],
                is_guessed=False,
                is_role_based=v["is_role_based"],
                verifier=v["verifier"],
                verified_at=v["verified_at"],
                source_url=fact.evidence_url,
                sourced_at=today,
            )
        )

    if company.owner_name and company.domain:
        local = company.owner_name.split()[0].lower()
        guessed = f"{local}@{company.domain}"
        if guessed not in seen and not is_role_email(guessed):
            v = verify_email(guessed, guessed=True)
            db.add(
                Contact(
                    company_id=company.id,
                    contact_type="email",
                    value=guessed,
                    status=v["status"],
                    is_guessed=True,
                    is_role_based=False,
                    verifier=v["verifier"],
                    verified_at=v["verified_at"],
                    source_url=company.website_url or company.source_url,
                    sourced_at=today,
                )
            )
