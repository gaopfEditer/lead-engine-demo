from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.lexbor import LexborHTMLParser

from app.settings import settings

_cache_robots: dict[str, RobotFileParser | None] = {}


def _robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _cache_robots:
        rp = RobotFileParser()
        try:
            rp.set_url(urljoin(base, "/robots.txt"))
            rp.read()
            _cache_robots[base] = rp
        except Exception:
            _cache_robots[base] = None
    rp = _cache_robots[base]
    if rp is None:
        return True
    return rp.can_fetch(settings.user_agent, url)


def fetch_html(url: str) -> tuple[str | None, str | None]:
    if not _robots_allowed(url):
        return None, "robots_disallow"
    time.sleep(0.05)
    try:
        with httpx.Client(timeout=20, headers={"User-Agent": settings.user_agent}) as client:
            r = client.get(url)
            if r.status_code >= 400:
                return None, f"http_{r.status_code}"
            return r.text, None
    except Exception as exc:
        return None, str(exc)


def extract_links(html: str, base_url: str) -> list[str]:
    tree = LexborHTMLParser(html)
    links: list[str] = []
    for node in tree.css("a"):
        href = node.attributes.get("href")
        if not href:
            continue
        links.append(urljoin(base_url, href))
    return links


def pick_paths(base_url: str, html: str) -> list[str]:
    keywords = ("about", "team", "contact", "career", "job", "staff")
    paths = {base_url}
    for link in extract_links(html, base_url):
        low = link.lower()
        if any(k in low for k in keywords):
            paths.add(link.split("#")[0])
    return list(paths)[:6]
