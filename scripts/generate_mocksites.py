#!/usr/bin/env python3
"""Generate synthetic contractor mock websites mapped to CSLB license numbers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))
from app.services.privacy import mask_person_name  # noqa: E402

DATA = ROOT / "data"
MOCK = ROOT / "mocksites"
SITES = MOCK / "sites"

ARCHETYPES = [
    "hot_lead",
    "hiring_signal",
    "tech_stack",
    "owner_match",
    "role_email",
    "catch_all_email",
    "franchise",
    "solo_shop",
    "no_team",
    "facebook_only",
    "invalid_mx",
    "guessed_only",
    "warm_lead",
    "cold_lead",
    "duplicate_domain_a",
    "duplicate_domain_b",
]


def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title}</title></head>
<body><header><h1>{title}</h1></header><main>{body}</main>
<footer><small>Synthetic demo site — not a real business.</small></footer></body></html>"""


def build_site(slug: str, archetype: str, owner: str, company: str) -> dict:
    base = SITES / slug
    base.mkdir(parents=True, exist_ok=True)
    domain = f"{slug}.demo.local"
    owner_first = owner.split()[0].lower() if owner else "owner"

    if archetype == "facebook_only":
        return {
            "slug": slug,
            "website_url": "",
            "archetype": archetype,
            "notes": "Facebook-only presence",
        }

    pages: dict[str, str] = {}
    contact_email = f"{owner_first}@{domain}"
    if archetype == "role_email":
        contact_email = f"info@{domain}"
    if archetype == "catch_all_email":
        domain = "catchall-demo.local"
        contact_email = f"{owner_first}@{domain}"
    if archetype == "invalid_mx":
        domain = "invalid-mx-demo.local"
        contact_email = f"{owner_first}@{domain}"

    pages["index.html"] = _page(
        company,
        f"<p>Licensed California contractor serving local homes and businesses.</p>"
        f"<p><a href=\"about.html\">About</a> | <a href=\"contact.html\">Contact</a></p>",
    )
    team_html = f"<p>Leadership: <strong>{owner}</strong> — Owner</p>" if owner else "<p>Small crew.</p>"
    if archetype in ("hot_lead", "hiring_signal", "tech_stack", "owner_match", "warm_lead"):
        team_html += "<p>Our field supervisors manage multi-crew projects.</p>"
    if archetype in ("solo_shop", "no_team"):
        team_html = "<p>Owner-operator shop.</p>"
    pages["about.html"] = _page(f"About {company}", team_html)
    mail = f"<a href=\"mailto:{contact_email}\">{contact_email}</a>"
    pages["contact.html"] = _page("Contact", f"<p>Email: {mail}</p><p>Phone: (555) 010-0000</p>")

    if archetype in ("hot_lead", "hiring_signal", "warm_lead"):
        pages["careers.html"] = _page(
            "Careers",
            "<p>Now hiring: HVAC technician, plumbing apprentice.</p><p>Join our growing team.</p>",
        )
    if archetype == "tech_stack":
        pages["about.html"] = _page(
            f"About {company}",
            team_html + "<p>We run operations on ServiceTitan.</p>",
        )
    if archetype == "franchise":
        pages["about.html"] = _page(
            f"About {company}",
            "<p>Proud franchise location — franchising opportunities available nationwide.</p>",
        )

    if archetype.startswith("duplicate_domain"):
        domain = "shared-duplicate.demo.local"
        contact_email = f"ops@{domain}"

    for name, html in pages.items():
        (base / name).write_text(html, encoding="utf-8")

    return {
        "slug": slug,
        "website_url": f"__MOCK__/{slug}/",
        "domain": domain,
        "archetype": archetype,
        "owner_hint": owner,
    }


def main() -> None:
    csv_path = DATA / "cslb_sample.csv"
    licenses: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("record_type") or "license").lower() != "license":
                continue
            licenses.append(row)

    registry: dict[str, dict] = {}
    SITES.mkdir(parents=True, exist_ok=True)
    (MOCK / "index.html").write_text(
        _page("Mock Contractor Sites", "<p>Directory of synthetic demo contractor websites.</p>"),
        encoding="utf-8",
    )

    for idx, row in enumerate(licenses):
        lic = str(row["LicenseNumber"])
        slug = f"contractor-{lic}"
        archetype = ARCHETYPES[idx % len(ARCHETYPES)]
        owner = ""
        registry[lic] = build_site(slug, archetype, owner, row.get("BusinessName") or slug)

    first_personnel: dict[str, str] = {}
    business_names: dict[str, str] = {
        str(row["LicenseNumber"]): row.get("BusinessName") or ""
        for row in licenses
    }

    # attach CSLB personnel to About/team pages (masked) for owner cross-check in the demo
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("record_type") or "").lower() != "personnel":
                continue
            lic = str(row.get("LicenseNumber"))
            if lic not in registry:
                continue
            name = (row.get("PersonnelName") or row.get("Name") or "").strip()
            if not name:
                continue
            first_personnel.setdefault(lic, name)
            title = (row.get("PersonnelTitle") or "").lower()
            if "owner" in title or "officer" in title or "president" in title or registry[lic]["archetype"] == "owner_match":
                display_name = mask_person_name(name, license_number=lic)
                registry[lic]["owner_hint"] = display_name
                if registry[lic].get("slug"):
                    build_site(
                        registry[lic]["slug"],
                        registry[lic]["archetype"],
                        display_name,
                        business_names.get(lic) or registry[lic]["slug"],
                    )

    for lic, name in first_personnel.items():
        if registry[lic].get("owner_hint") or not registry[lic].get("slug"):
            continue
        display_name = mask_person_name(name, license_number=lic)
        registry[lic]["owner_hint"] = display_name
        build_site(
            registry[lic]["slug"],
            registry[lic]["archetype"],
            display_name,
            business_names.get(lic) or registry[lic]["slug"],
        )

    (DATA / "mock_site_registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(f"Generated {len(registry)} mock sites")


if __name__ == "__main__":
    main()
