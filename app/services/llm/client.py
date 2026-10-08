from __future__ import annotations

import json
from typing import Any

import httpx

from app.settings import settings


def llm_available() -> bool:
    return bool(settings.llm_api_key and settings.llm_base_url)


def chat_json(system: str, user: str) -> dict[str, Any] | None:
    if not llm_available():
        return None
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return None
