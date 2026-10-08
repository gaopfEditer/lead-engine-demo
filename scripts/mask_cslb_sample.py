#!/usr/bin/env python3
"""Mask personnel names in committed cslb_sample.csv and record pre-mask hashes for tests."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.privacy import hash_personnel_name, mask_person_name  # noqa: E402

DATA = ROOT / "data"
CSV_PATH = DATA / "cslb_sample.csv"
HASH_PATH = DATA / "cslb_personnel_name_hashes.txt"
META_PATH = DATA / "cslb_sample.meta.json"


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(f"Missing {CSV_PATH}")

    rows: list[dict] = []
    banned_hashes: list[str] = []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            if (row.get("record_type") or "").lower() == "personnel":
                raw = (row.get("PersonnelName") or row.get("Name") or "").strip()
                if raw:
                    banned_hashes.append(hash_personnel_name(raw))
                    lic = str(row.get("LicenseNumber") or "")
                    row["PersonnelName"] = mask_person_name(raw, license_number=lic)
            rows.append(row)

    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    HASH_PATH.write_text("\n".join(sorted(set(banned_hashes))) + "\n", encoding="utf-8")

    meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    meta["personnel_names_masked"] = True
    meta["personnel_name_hash_count"] = len(set(banned_hashes))
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Masked personnel in {CSV_PATH.name}; {len(set(banned_hashes))} name hashes -> {HASH_PATH.name}")


if __name__ == "__main__":
    main()
