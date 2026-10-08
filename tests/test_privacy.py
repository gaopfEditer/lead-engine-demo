from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.services.privacy import (
    hash_personnel_name,
    looks_like_personal_business_name,
    looks_like_unmasked_personnel_name,
    mask_person_name,
    mask_sole_proprietor_business_name,
    should_mask_business_name,
)
from app.db.models import Company

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "demo_snapshot" / "lead_engine.db"
HASH_PATH = ROOT / "data" / "cslb_personnel_name_hashes.txt"


def test_mask_person_name_cslb_format():
    masked = mask_person_name("SCHELL                             JAKOB          CLARK", license_number="22726")
    assert masked == "Jakob S."
    assert not looks_like_unmasked_personnel_name(masked)


def test_sole_proprietor_business_name_heuristic():
    assert looks_like_personal_business_name("KEENE MICHAEL WAYNE")
    assert not looks_like_personal_business_name("LOPEZ ELECTRIC")
    masked = mask_sole_proprietor_business_name("KEENE MICHAEL WAYNE", license_number="831991")
    assert masked == "Michael K. (Sole Proprietor)"


def test_should_mask_sole_owner_company():
    company = Company(
        license_number="831991",
        business_name="KEENE MICHAEL WAYNE",
        business_type="Sole Owner",
        source_url="https://example.com",
        sourced_at="2026-01-01",
    )
    assert should_mask_business_name(company)


def test_mask_person_name_idempotent():
    once = mask_person_name("TORRES                             ADALBERTO", license_number="1")
    twice = mask_person_name(once, license_number="1")
    assert once == twice == "Adalberto T."


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="demo snapshot not built")
def test_snapshot_has_no_unmasked_personnel_names():
    assert HASH_PATH.exists(), "missing personnel hash blocklist (run scripts/mask_cslb_sample.py)"
    banned = {line.strip() for line in HASH_PATH.read_text().splitlines() if line.strip()}

    conn = sqlite3.connect(SNAPSHOT)
    try:
        people = [r[0] for r in conn.execute("SELECT name FROM people").fetchall()]
        owners = [r[0] for r in conn.execute("SELECT owner_name FROM companies WHERE owner_name IS NOT NULL").fetchall()]
        team_facts = [
            r[0]
            for r in conn.execute("SELECT value FROM facts WHERE kind = 'team_member'").fetchall()
        ]
        sole_business = conn.execute(
            "SELECT business_name FROM companies WHERE business_type = 'Sole Owner'"
        ).fetchall()
        websites = conn.execute(
            "SELECT website_url FROM companies WHERE website_url IS NOT NULL"
        ).fetchall()
        first_lines = [r[0] for r in conn.execute("SELECT first_line FROM drafts").fetchall()]
    finally:
        conn.close()

    for name in people + owners + team_facts:
        assert name
        assert hash_personnel_name(name) not in banned
        assert not looks_like_unmasked_personnel_name(name), f"unmasked-looking name in snapshot: {name!r}"

    for (bn,) in sole_business:
        assert bn
        raw = bn.split(" (Sole Proprietor)")[0]
        if looks_like_personal_business_name(raw):
            assert "(Sole Proprietor)" in bn, f"unmasked sole-prop business name in snapshot: {bn!r}"
        assert hash_personnel_name(raw) not in banned

    for (url,) in websites:
        assert "127.0.0.1" not in url
        assert "localhost" not in url

    assert not any((v or "").startswith("About") for v in team_facts)
    assert not any("About C." in (line or "") for line in first_lines)
