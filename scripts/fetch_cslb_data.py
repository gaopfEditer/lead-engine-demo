#!/usr/bin/env python3
"""Download a CSLB subset (License Master + Personnel) for selected counties/classes."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"


def download_county_export(counties: list[str], classifications: list[str], dest: Path) -> Path:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto("https://www.cslb.ca.gov/OnlineServices/DataPortal/ListByCounty.aspx", wait_until="networkidle")
        county_map = page.eval_on_selector(
            "#lbCounty", "el => Object.fromEntries(Array.from(el.options).map(o => [o.text, o.value]))"
        )
        class_map = page.eval_on_selector(
            "#lbClassification",
            "el => Object.fromEntries(Array.from(el.options).map(o => [o.text.split(' - ')[0], o.value]))",
        )
        county_values = [county_map[c] for c in counties]
        class_values = [class_map[c] for c in classifications]
        page.evaluate(
            """(payload) => {
            const county = document.querySelector('#lbCounty');
            for (const opt of county.options) opt.selected = payload.counties.includes(opt.value);
            county.dispatchEvent(new Event('change', {bubbles:true}));
            const cls = document.querySelector('#lbClassification');
            for (const opt of cls.options) opt.selected = payload.classes.includes(opt.value);
            cls.dispatchEvent(new Event('change', {bubbles:true}));
        }""",
            {"counties": county_values, "classes": class_values},
        )
        with page.expect_download(timeout=300000) as dl_info:
            page.click("#btnSearch")
        download = dl_info.value
        dest.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(dest)
        browser.close()
    return dest


def download_personnel(dest: Path) -> Path:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto("https://www.cslb.ca.gov/OnlineServices/DataPortal/ContractorList.aspx", wait_until="networkidle")
        page.select_option("#MainContent_ddlStatus", "P")
        page.wait_for_timeout(1000)
        with page.expect_download(timeout=600000) as dl_info:
            page.click("#MainContent_lbtnPersonnelcsv")
        download = dl_info.value
        download.save_as(dest)
        browser.close()
    return dest


def build_sample(license_xlsx: Path, personnel_csv: Path, out_csv: Path, meta_path: Path, limit: int = 120) -> None:
    import pandas as pd

    lic = pd.read_excel(license_xlsx).head(limit)
    lic_ids = {int(x) for x in lic["LicenseNumber"]}
    personnel_rows = []
    with personnel_csv.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ln = int(row["LIC-NO"])
            except Exception:
                continue
            if ln in lic_ids:
                personnel_rows.append(row)

    rows = []
    for _, r in lic.iterrows():
        rows.append(
            {
                "record_type": "license",
                "LicenseNumber": int(r["LicenseNumber"]),
                "BusinessType": r.get("BusinessType", ""),
                "BusinessName": r.get("BusinessName", ""),
                "Address": r.get("Address", ""),
                "City": r.get("City", ""),
                "State": r.get("State", ""),
                "ZIP Code": r.get("ZIP Code", ""),
                "County": r.get("County", ""),
                "PhoneNumber": r.get("PhoneNumber", ""),
                "IssueDate": str(r.get("IssueDate", "")),
                "ExpirationDate": str(r.get("ExpirationDate", "")),
                "Classification(s)": str(r.get("Classification(s)", "")),
                "Status": r.get("Status", ""),
                "PersonnelName": "",
                "PersonnelTitle": "",
            }
        )
    for pr in personnel_rows:
        rows.append(
            {
                "record_type": "personnel",
                "LicenseNumber": int(pr["LIC-NO"]),
                "BusinessType": "",
                "BusinessName": "",
                "Address": "",
                "City": "",
                "State": "",
                "ZIP Code": "",
                "County": "",
                "PhoneNumber": "",
                "IssueDate": "",
                "ExpirationDate": "",
                "Classification(s)": pr.get("CL-CDE", ""),
                "Status": "",
                "PersonnelName": pr.get("Name", ""),
                "PersonnelTitle": pr.get("EMP-Titl-CDE", ""),
            }
        )
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    meta = {
        "source_url": "https://www.cslb.ca.gov/OnlineServices/DataPortal/ListByCounty.aspx",
        "download_date": "2026-10-08",
        "counties": ["Alameda", "Sacramento"],
        "classifications": ["C-10", "C-20", "C-36"],
        "synthetic": False,
        "personnel_rows": len(personnel_rows),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()
    license_xlsx = OUT / "cslb_raw_counties.xlsx"
    personnel_csv = OUT / "cslb_personnel_full.csv"
    if not args.skip_download:
        download_county_export(["Alameda", "Sacramento"], ["C-10", "C-20", "C-36"], license_xlsx)
        download_personnel(personnel_csv)
    build_sample(license_xlsx, personnel_csv, OUT / "cslb_sample.csv", OUT / "cslb_sample.meta.json")


if __name__ == "__main__":
    main()
