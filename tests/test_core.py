from __future__ import annotations

from app.db.models import Fact
from app.services.dedupe import _union_find
from app.services.llm.grounding import validate_reasons
from app.services.normalize import is_role_email, normalize_address, normalize_phone
from app.services.score import hard_exclude, load_icp, rule_score
from app.services.verify import exportable_status, verify_email


class DummyCompany:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class DummyFact:
    def __init__(self, id, kind, value, snippet, evidence_url="http://example.com"):
        self.id = id
        self.kind = kind
        self.value = value
        self.snippet = snippet
        self.evidence_url = evidence_url


def test_phone_normalization():
    e164, ptype = normalize_phone("(510) 686-9900")
    assert e164 == "+15106869900"
    assert ptype in {"landline", "mobile", "unknown"}


def test_address_normalization():
    a = normalize_address("1933 Williams St", "San Leandro", "CA", "94577")
    assert "WILLIAMS" in a
    assert "94577" in a


def test_role_email_exclusion():
    assert is_role_email("info@example.com")
    assert not exportable_status("role_based", False)


def test_guessed_email_excluded_from_export():
    assert not exportable_status("ok", True)
    assert exportable_status("ok", False)


def test_verify_email_mock_deterministic():
    a = verify_email("alice@ok-mail-demo.local")
    b = verify_email("alice@ok-mail-demo.local")
    assert a["status"] == b["status"]


def test_dedupe_union_find():
    roots = _union_find([1, 2, 3, 4], [(1, 2), (3, 4)])
    assert roots[1] == roots[2]
    assert roots[3] == roots[4]
    assert roots[1] != roots[3]


def test_grounding_validator_drops_ungrounded():
    facts = [Fact(id=1, company_id=1, kind="hiring", value="2 roles", evidence_url="u", snippet="Now hiring technician", observed_at="2026-01-01")]
    valid = validate_reasons(
        [
            {"fact_id": 1, "text": "Hiring", "snippet": "Now hiring technician"},
            {"fact_id": 1, "text": "Fake", "snippet": "not in source"},
            {"fact_id": 99, "text": "Missing fact", "snippet": "x"},
        ],
        facts,
    )
    assert len(valid) == 1
    assert valid[0]["fact_id"] == 1


def test_offline_scoring_hard_exclude_franchise():
    icp = load_icp()
    company = DummyCompany(
        website_url="http://x",
        years_in_business=15,
        county="Alameda",
        license_status="CLEAR",
        suppressed=False,
        is_primary_in_cluster=True,
        business_name="LOCAL CO",
        facts=[DummyFact(1, "franchise", "franchise_indicator", "franchise")],
        signals=[],
        people=[],
        contacts=[],
    )
    assert hard_exclude(company, icp) == "franchise"


def test_suppression_role_guessed_flags():
    assert verify_email("info@test.com")["status"] == "role_based"
    assert verify_email("john@catchall-demo.local")["status"] == "catch_all"
