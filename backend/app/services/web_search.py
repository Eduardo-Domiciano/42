from __future__ import annotations

import logging
import time
from datetime import date

from duckduckgo_search import DDGS

from app.config import settings
from app.services.topic_relevance import build_search_query

logger = logging.getLogger(__name__)


def search_news_urls(
    query: str,
    *,
    max_results: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    refine_query: bool = True,
) -> list[str]:
    """
    Busca URLs. Prioriza news (DDG text tem falhado vazio / rate-limit no BR).
    Com período curto, aplica timelimit w/m.
    """
    limit = max_results or settings.crossref_max_peers
    has_range = bool(date_from or date_to)

    if refine_query:
        q_text = build_search_query(query, for_news=False)
        q_news = build_search_query(query, for_news=True)
    else:
        q_text = query.strip()
        q_news = query.strip()

    timelimit = None
    if date_from and date_to:
        days = (date_to - date_from).days
        if days <= 7:
            timelimit = "w"
        elif days <= 31:
            timelimit = "m"

    urls: list[str] = []
    seen: set[str] = set()

    def _add(url: str | None) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        urls.append(url)

    def _news(ddgs: DDGS, q: str, n: int) -> None:
        for item in (
            ddgs.news(
                q,
                region="br-pt",
                timelimit=timelimit if has_range else None,
                max_results=n,
            )
            or []
        ):
            _add(item.get("url") or item.get("href"))

    def _text(ddgs: DDGS, q: str, n: int) -> None:
        for item in (
            ddgs.text(
                q,
                region="br-pt",
                timelimit=timelimit if has_range else None,
                max_results=n,
            )
            or []
        ):
            _add(item.get("href"))

    # Poucas chamadas: DDG rate-limita fácil se text+news+site repetem.
    attempts = (
        ("news", q_news, limit),
        ("news", f"{q_news} site:.br", max(8, limit // 2)),
        ("text", q_text, max(8, limit // 2)),
    )

    def _run_pass() -> None:
        with DDGS() as ddgs:
            for kind, q, n in attempts:
                if len(urls) >= limit:
                    break
                before = len(urls)
                try:
                    if kind == "news":
                        _news(ddgs, q, n)
                    else:
                        _text(ddgs, q, n)
                except Exception as exc:
                    logger.warning("DDG %s falhou (%s): %s", kind, q[:60], exc)
                    time.sleep(0.7)
                    continue
                if len(urls) == before:
                    time.sleep(0.4)

    try:
        _run_pass()
        if not urls:
            time.sleep(1.2)
            _run_pass()
    except Exception as exc:
        logger.warning("DDG sessão falhou: %s", exc)

    if not urls:
        logger.warning("DDG sem URLs para query=%r", query[:120])

    return urls[:limit]
