from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings


def llm_configured() -> bool:
    return bool(settings.openrouter_api_key)


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.1,
) -> dict[str, Any] | None:
    if not llm_configured():
        return None

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/42",
        "X-Title": "④②",
    }
    payload = {
        "model": settings.openrouter_model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_json_content(content)
    except Exception:
        return None


def _parse_json_content(content: str) -> dict[str, Any] | None:
    content = content.strip()
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
