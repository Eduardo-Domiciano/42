"""Juiz LLM leve: valida contexto tema × artigo — um candidato por vez."""

from __future__ import annotations

import logging

from app.config import settings
from app.models import Article
from app.services.llm_client import chat_json, llm_configured

logger = logging.getLogger(__name__)

_SYSTEM = """Você filtra notícias brasileiras por relevância ao tema buscado.
Responda APENAS JSON:
{"relevant":true,"confidence":0.0,"reason":"curta"}
Regras:
- relevant=true se o artigo trata o MESMO assunto/contexto do tema (mesmo com outras palavras).
- relevant=false se só compartilha nome genérico, pessoa diferente, ou é outro caso/notícia.
- Seja maleável com sinônimos; rigoroso com troca de tema.
- confidence de 0 a 1.
"""


def llm_relevance_available() -> bool:
    return settings.topic_relevance_use_llm and llm_configured()


def judge_topic_relevance_one(
    topic: str,
    article: Article,
) -> tuple[bool, float, str] | None:
    """Avalia um único artigo. None se a LLM falhar."""
    if not llm_relevance_available():
        return None

    title = (article.title or "Sem título").strip()
    snippet = ((article.excerpt or "") or (article.body or ""))[:220].strip()
    user = (
        f"Tema: {topic.strip()}\n"
        f"id={article.id}\n"
        f"Título: {title}\n"
        f"Trecho: {snippet or '(vazio)'}\n"
        "Este artigo é sobre o mesmo assunto do tema?"
    )
    data = chat_json(
        _SYSTEM,
        user,
        temperature=0.05,
        model=settings.topic_relevance_llm_model or settings.local_llm_model,
        timeout=settings.topic_relevance_llm_timeout,
    )
    if not data or "relevant" not in data:
        logger.warning("LLM relevância: falha no id=%s", article.id)
        return None
    relevant = bool(data.get("relevant"))
    try:
        conf = float(data.get("confidence") or 0.5)
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    reason = str(
        data.get("reason") or ("relevante" if relevant else "fora do tema")
    )[:180]
    return relevant, conf, reason


def judge_topic_relevance_batch(
    topic: str,
    articles: list[Article],
    *,
    stop_when_relevant: int | None = None,
) -> dict[int, tuple[bool, float, str]]:
    """
    Processa um artigo por chamada (mais leve que um prompt gigante).
    Para cedo se já houver stop_when_relevant aceites (opcional).
    """
    if not llm_relevance_available() or not articles:
        return {}

    limit = max(1, settings.topic_relevance_llm_max)
    out: dict[int, tuple[bool, float, str]] = {}
    relevant_n = 0
    for art in articles[:limit]:
        verdict = judge_topic_relevance_one(topic, art)
        if verdict is None:
            continue
        out[art.id] = verdict
        if verdict[0] and verdict[1] >= 0.35:
            relevant_n += 1
            if stop_when_relevant and relevant_n >= stop_when_relevant:
                logger.info(
                    "LLM relevância: parou cedo (%s relevantes)", relevant_n
                )
                break
    return out
