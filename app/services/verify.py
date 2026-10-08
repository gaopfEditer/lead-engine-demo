from __future__ import annotations

import datetime as dt
import re

import dns.resolver
from email_validator import EmailNotValidError, validate_email

from app.services.normalize import is_role_email
from app.settings import settings

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Deterministic mock domains for demo edge cases
MOCK_DOMAIN_STATUS: dict[str, str] = {
    "catchall-demo.local": "catch_all",
    "invalid-mx-demo.local": "invalid",
    "ok-mail-demo.local": "ok",
}


def syntax_ok(email: str) -> bool:
    domain = email.split("@", 1)[-1]
    if domain.endswith(".demo.local"):
        return bool(EMAIL_RE.match(email))
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def mx_exists(domain: str) -> bool:
    if domain.endswith(".demo.local") or domain in MOCK_DOMAIN_STATUS:
        return True
    if domain.endswith(".local"):
        return False
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


def verify_email(email: str, *, guessed: bool = False) -> dict:
    email = email.strip().lower()
    today = dt.date.today().isoformat()
    result = {
        "email": email,
        "status": "unknown",
        "is_role_based": is_role_email(email),
        "is_guessed": guessed,
        "verifier": settings.email_verifier,
        "verified_at": today,
    }
    domain = email.split("@", 1)[1]
    if domain in MOCK_DOMAIN_STATUS:
        result["status"] = MOCK_DOMAIN_STATUS[domain]
        return result
    if not syntax_ok(email):
        result["status"] = "invalid"
        return result
    if result["is_role_based"]:
        result["status"] = "role_based"
        return result
    if guessed:
        result["status"] = "guessed"
        return result
    if not mx_exists(domain):
        result["status"] = "invalid"
        return result
    if settings.email_verifier == "mock":
        if domain.endswith(".demo.local"):
            bucket = sum(ord(c) for c in email) % 10
            if domain.startswith("invalid-mx"):
                result["status"] = "invalid"
            elif bucket <= 6:
                result["status"] = "ok"
            elif bucket == 7:
                result["status"] = "catch_all"
            else:
                result["status"] = "unknown"
            return result
        bucket = sum(ord(c) for c in email) % 10
        if bucket <= 5:
            result["status"] = "ok"
        elif bucket == 6:
            result["status"] = "catch_all"
        elif bucket == 7:
            result["status"] = "unknown"
        else:
            result["status"] = "invalid"
        return result
    result["status"] = "unknown"
    return result


def exportable_status(status: str, is_guessed: bool) -> bool:
    return status == "ok" and not is_guessed
