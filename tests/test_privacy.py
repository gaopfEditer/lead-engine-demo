from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.services.privacy import (
    hash_personnel_name,
    looks_like_unmasked_personnel_name,
    mask_person_name,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "demo_snapshot" / "lead_engine.db"
HASH_PATH = ROOT / "data" / "cslb_personnel_name_hashes.txt"


def test_mask_person_name_cslb_format():
    masked = mask_person_name("SCHELL                             JAKOB          CLARK", license_number="22726")
    assert masked == "Jakob S."
    assert not looks_like_unmasked_personnel_name(masked)


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
    finally:
        conn.close()

    for name in people + owners + team_facts:
        assert name
        assert hash_personnel_name(name) not in banned
        assert not looks_like_unmasked_personnel_name(name), f"unmasked-looking name in snapshot: {name!r}"
