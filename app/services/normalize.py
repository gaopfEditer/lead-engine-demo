from __future__ import annotations

import re

import phonenumbers

ROLE_EMAIL_LOCALS = {
    "info",
    "admin",
    "contact",
    "office",
    "sales",
    "support",
    "hello",
    "service",
    "billing",
    "hr",
    "jobs",
    "careers",
}


def normalize_phone(raw: str | None) -> tuple[str | None, str | None]:
    if not raw:
        return None, None
    cleaned = re.sub(r"[^\d+]", "", raw)
    try:
        num = phonenumbers.parse(cleaned if cleaned.startswith("+") else f"+1{cleaned}", None)
        if not phonenumbers.is_possible_number(num):
            return None, "unknown"
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        ntype = phonenumbers.number_type(num)
        if ntype in (phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE):
            ptype = "mobile"
        elif ntype == phonenumbers.PhoneNumberType.TOLL_FREE:
            ptype = "toll-free"
        elif ntype == phonenumbers.PhoneNumberType.FIXED_LINE:
            ptype = "landline"
        else:
            ptype = "unknown"
        return e164, ptype
    except phonenumbers.NumberParseException:
        return None, "unknown"


def normalize_address(address: str | None, city: str | None, state: str | None, zip_code: str | None) -> str:
    parts = [address or "", city or "", state or "", str(zip_code or "")]
    joined = " ".join(p.strip() for p in parts if p and str(p).strip())
    joined = re.sub(r"\s+", " ", joined.upper())
    joined = re.sub(r"\b(STREET|ST\.|ST)\b", "ST", joined)
    joined = re.sub(r"\b(ROAD|RD\.|RD)\b", "RD", joined)
    joined = re.sub(r"\b(AVENUE|AVE\.|AVE)\b", "AVE", joined)
    joined = re.sub(r"[^A-Z0-9 ]", "", joined)
    return joined.strip()


def extract_domain(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip().lower()
    if url.startswith("http"):
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
    else:
        host = url.split("/")[0]
    host = host.removeprefix("www.")
    return host or None


def is_role_email(email: str) -> bool:
    local = email.split("@", 1)[0].lower()
    return local in ROLE_EMAIL_LOCALS or local.startswith("noreply")


def normalize_business_name(name: str) -> str:
    n = name.upper()
    for token in ("LLC", "INC", "CORP", "CO", "LTD", "."):
        n = n.replace(token, " ")
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    return re.sub(r"\s+", " ", n).strip()
