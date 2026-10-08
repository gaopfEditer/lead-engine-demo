#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = [
    ("pipeline", "/"),
    ("leads", "/leads"),
    ("lead_detail", "/leads/1"),
    ("icp", "/icp"),
    ("quality", "/quality"),
    ("sync", "/sync"),
]

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        for name, path in PAGES:
            url = BASE + path
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print("saved", name)
        browser.close()


if __name__ == "__main__":
    main()
