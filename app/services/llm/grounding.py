from __future__ import annotations

from typing import Any

from app.db.models import Fact


def validate_reasons(reasons: list[dict[str, Any]], facts: list[Fact]) -> list[dict[str, Any]]:
    by_id = {f.id: f for f in facts}
    valid: list[dict[str, Any]] = []
    for reason in reasons:
        fact_id = reason.get("fact_id")
        if fact_id is None:
            continue
        fact = by_id.get(int(fact_id))
        if not fact:
            continue
        snippet = (reason.get("snippet") or reason.get("text") or "").strip()
        if not snippet:
            continue
        hay = f"{fact.value}\n{fact.snippet}".lower()
        if snippet.lower() not in hay:
            continue
        valid.append(
            {
                "fact_id": fact.id,
                "text": reason.get("text") or snippet,
                "evidence_url": fact.evidence_url,
                "snippet": fact.snippet,
            }
        )
    return valid
