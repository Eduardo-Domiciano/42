from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Uma chamada por vez no Ollama — evita sobrecarga / OOM em modelo leve.
_LLM_LOCK = threading.Lock()


def llm_provider() -> str:
    return (settings.llm_provider or "local").strip().lower()


def llm_configured() -> bool:
    """LLM ativa só se provider ≠ none e endpoint/chave ok."""
    prov = llm_provider()
    if prov in {"", "none", "off", "disabled"}:
        return False
    if prov == "openrouter":
        return bool(settings.openrouter_api_key)
    if prov == "local":
        return bool(settings.llm_base_url)
    return False


def effective_model(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if llm_provider() == "openrouter":
        return settings.openrouter_model
    return settings.local_llm_model or "gemma3:4b"


def _endpoint() -> str:
    if llm_provider() == "openrouter":
        return "https://openrouter.ai/api/v1/chat/completions"
    base = settings.llm_base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _headers() -> dict[str, str]:
    if llm_provider() == "openrouter":
        return {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost/42",
            "X-Title": "Projeto42",
        }
    # Ollama / servidores OpenAI-compat aceitam Bearer opcional
    key = settings.llm_api_key or "ollama"
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _chat_raw(
    system: str,
    user: str,
    *,
    temperature: float = 0.1,
    model: str | None = None,
    timeout: float | None = None,
    json_object: bool = True,
) -> str | None:
    if not llm_configured():
        return None

    payload: dict[str, Any] = {
        "model": effective_model(model),
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    # OpenRouter aceita json_object; Ollama local costuma ir melhor só com prompt
    if json_object and llm_provider() == "openrouter":
        payload["response_format"] = {"type": "json_object"}

    try:
        with _LLM_LOCK:
            with httpx.Client(timeout=timeout or settings.llm_timeout_seconds) as client:
                response = client.post(
                    _endpoint(),
                    headers=_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("LLM (%s) falhou: %s", llm_provider(), exc)
        return None


def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.1,
    model: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any] | None:
    content = _chat_raw(
        system,
        user,
        temperature=temperature,
        model=model,
        timeout=timeout,
        json_object=True,
    )
    if not content:
        return None
    return _parse_json_content(content)


def _parse_json_content(content: str) -> dict[str, Any] | None:
    content = content.strip()
    # Remove cercas markdown se o modelo local embelezar
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
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
