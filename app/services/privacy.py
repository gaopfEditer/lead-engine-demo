from __future__ import annotations

import hashlib
import re
from copy import copy

from app.db.models import Company, Draft, Fact, Person

_MASKED_RE = re.compile(r"^[A-Z][a-z]+(?:['-][A-Z][a-z]+)* [A-Z]\.$")
_PSEUDONYM_RE = re.compile(r"^Demo Contact [0-9a-f]{4}$")
_SOLE_PROP_BUSINESS_RE = re.compile(r"^[^:]+:\s*\(Sole Proprietor\)$")
_BUSINESS_TRADE_WORDS = re.compile(
    r"\b("
    r"ELECTRIC|ELECTRICAL|CONSTRUCTION|CONTRACTOR|PLUMBING|HVAC|SERVICE|SERVICES|"
    r"ENTERPRISE|ENTERPRISES|DESIGN|SECURITY|SOUND|IMPROVEMENT|COMPANY|LLC|INC|CORP|"
    r"GROUP|TEAM|HOME|HOUSE|BAY|ACE|GREEN|LIGHT|CONNECTED|PARAGON|SAFE|NELSON|SOLEIL|"
    r"MIGHTY|ELITE|PRO|PROFESSIONAL|MAINTENANCE|REPAIR|SYSTEMS|SOLAR|POWER|WIRE|WIRING|"
    r"CONTRACTING|BUILDERS|BUILDER|REMODEL|HANDYMAN|INSTALLATION"
    r")\b",
    re.I,
)


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


def looks_like_personal_business_name(name: str) -> bool:
    """Heuristic: CSLB-style personal name used as the public business name."""
    raw = (name or "").strip()
    if not raw or _SOLE_PROP_BUSINESS_RE.match(raw):
        return False
    if _BUSINESS_TRADE_WORDS.search(raw):
        return False
    parts = _tokens(raw)
    if len(parts) < 2 or len(parts) > 4:
        return False
    if parts[0].isupper() and parts[1].isupper() and any(c.isalpha() for c in parts[0]):
        return True
    if all(re.match(r"^[A-Z][a-z'-]+$", p) for p in parts[:2]):
        return True
    return False


def _masked_person_matches_business(person_name: str, business_raw: str) -> bool:
    person_name = (person_name or "").strip()
    if not person_name or not _MASKED_RE.match(person_name):
        return False
    parsed = parse_person_parts(business_raw)
    if not parsed:
        return False
    b_first, b_last = parsed
    m = re.match(r"^([A-Z][a-z]+(?:['-][A-Z][a-z]+)*) ([A-Z])\.$", person_name)
    if not m:
        return False
    p_first, p_li = m.group(1), m.group(2)
    if p_first.lower() != b_first.lower():
        return False
    return bool(b_last) and b_last[0].upper() == p_li.upper()


def should_mask_business_name(company: Company) -> bool:
    raw = (company.business_name or "").strip()
    if not raw or _SOLE_PROP_BUSINESS_RE.match(raw):
        return False
    bt = (company.business_type or "").lower()
    if "sole" in bt and looks_like_personal_business_name(raw):
        return True
    return any(_masked_person_matches_business(p.name, raw) for p in company.people)


def mask_sole_proprietor_business_name(raw: str, *, license_number: str = "") -> str:
    masked = mask_person_name(raw, license_number=license_number)
    return f"{masked} (Sole Proprietor)"


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
    raw_business_name = company.business_name
    c = copy(company)
    if should_mask_business_name(company):
        c.business_name = mask_sole_proprietor_business_name(raw_business_name, license_number=lic)
    if company.mock_site_slug:
        c.website_url = f"https://{company.mock_site_slug}.demo.local/"
    elif c.website_url and ("127.0.0.1" in c.website_url or "localhost" in c.website_url):
        c.website_url = None
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
        if raw_business_name and raw_business_name in (nd.first_line or ""):
            nd.first_line = (nd.first_line or "").replace(raw_business_name, c.business_name)
        drafts.append(nd)
    c.drafts = drafts
    return c


def scrub_export_row(row: dict, *, license_number: str = "", company: Company | None = None) -> dict:
    lic = license_number or str(row.get("license_number", ""))
    out = dict(row)
    raw_business = row.get("business_name") or ""
    if company is not None and should_mask_business_name(company):
        out["business_name"] = mask_sole_proprietor_business_name(raw_business, license_number=lic)
    if out.get("owner_name"):
        out["owner_name"] = mask_person_name(out["owner_name"], license_number=lic)
    line = out.get("first_line") or ""
    if line and out.get("owner_name"):
        raw_owner = row.get("owner_name") or ""
        if raw_owner and raw_owner in line:
            line = line.replace(raw_owner, out["owner_name"])
    out["first_line"] = line
    return out
