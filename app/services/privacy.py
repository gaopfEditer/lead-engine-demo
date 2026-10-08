from __future__ import annotations

import hashlib
import re
from copy import copy

from app.db.models import Company, Draft, Fact, Person

_MASKED_RE = re.compile(r"^[A-Z][a-z]+(?:['-][A-Z][a-z]+)* [A-Z]\.$")
_PSEUDONYM_RE = re.compile(r"^Demo Contact [0-9a-f]{4}$")


def _tokens(raw: str) -> list[str]:
    segment = raw.split("|")[0].strip()
    return [t for t in re.split(r"\s+", segment) if t]


def parse_person_parts(raw: str) -> tuple[str, str] | None:
    """Best-effort parse for CSLB-style 'LAST FIRST MIDDLE' or 'First Last'."""
    parts = _tokens(raw)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0].title(), ""
    # CSLB exports often use LAST FIRST [MIDDLE] in ALL CAPS.
    if parts[0].isupper() and any(c.isalpha() for c in parts[0]):
        last = parts[0]
        first = parts[1]
    else:
        first = parts[0]
        last = parts[-1]
    first = re.sub(r"[^A-Za-z'-]", "", first).title()
    last = re.sub(r"[^A-Za-z'-]", "", last)
    if not first:
        return None
    return first, last


def mask_person_name(raw: str, *, license_number: str = "") -> str:
    """Public-safe display name: 'Maria G.' or deterministic pseudonym."""
    raw = (raw or "").strip()
    if not raw:
        return "Demo Contact"
    if _MASKED_RE.match(raw) or _PSEUDONYM_RE.match(raw):
        return raw
    parsed = parse_person_parts(raw)
    if parsed:
        first, last = parsed
        if last:
            return f"{first} {last[0].upper()}."
        return first
    digest = hashlib.sha256(f"{license_number}:{raw}".encode()).hexdigest()[:4]
    return f"Demo Contact {digest}"


def looks_like_unmasked_personnel_name(name: str) -> bool:
    """Heuristic: CSLB padding / ALL CAPS personnel strings should not ship publicly."""
    if not name or name.strip() in {"", "—"}:
        return False
    if _MASKED_RE.match(name) or _PSEUDONYM_RE.match(name):
        return False
    if re.search(r"\s{4,}", name):
        return True
    letters = re.sub(r"[^A-Za-z]", "", name)
    if len(letters) >= 12 and name.upper() == name:
        return True
    return False


def hash_personnel_name(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def scrub_company(company: Company) -> Company:
    """Return a shallow copy with owner/people/facts/drafts masked for public display."""
    lic = company.license_number or ""
    c = copy(company)
    if c.owner_name:
        c.owner_name = mask_person_name(c.owner_name, license_number=lic)
    people: list[Person] = []
    for p in company.people:
        np = copy(p)
        np.name = mask_person_name(p.name, license_number=lic)
        people.append(np)
    c.people = people

    facts: list[Fact] = []
    for f in company.facts:
        nf = copy(f)
        if nf.kind == "team_member":
            nf.value = mask_person_name(nf.value, license_number=lic)
            nf.snippet = mask_person_name(nf.snippet, license_number=lic)
        facts.append(nf)
    c.facts = facts

    drafts: list[Draft] = []
    for d in company.drafts:
        nd = copy(d)
        if nd.first_line and company.owner_name:
            nd.first_line = nd.first_line.replace(
                company.owner_name,
                mask_person_name(company.owner_name, license_number=lic),
            )
        for p in company.people:
            masked = mask_person_name(p.name, license_number=lic)
            if p.name in (nd.first_line or ""):
                nd.first_line = (nd.first_line or "").replace(p.name, masked)
        for f in company.facts:
            if f.kind == "team_member" and f.value in (nd.first_line or ""):
                nd.first_line = (nd.first_line or "").replace(
                    f.value, mask_person_name(f.value, license_number=lic)
                )
        drafts.append(nd)
    c.drafts = drafts
    return c


def scrub_export_row(row: dict, *, license_number: str = "") -> dict:
    lic = license_number or str(row.get("license_number", ""))
    out = dict(row)
    if out.get("owner_name"):
        out["owner_name"] = mask_person_name(out["owner_name"], license_number=lic)
    line = out.get("first_line") or ""
    if line and out.get("owner_name"):
        raw_owner = row.get("owner_name") or ""
        if raw_owner and raw_owner in line:
            line = line.replace(raw_owner, out["owner_name"])
    out["first_line"] = line
    return out
