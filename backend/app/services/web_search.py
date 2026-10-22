from __future__ import annotations

from datetime import date

from duckduckgo_search import DDGS

from app.config import settings
from app.services.topic_relevance import build_search_query


def search_news_urls(
    query: str,
    *,
    max_results: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    refine_query: bool = True,
) -> list[str]:
    """
    Busca URLs. Sem período: prioriza text (histórico) e completa com news.
    Com período: news + text, com timelimit só se o intervalo for curto.
    """
    limit = max_results or settings.crossref_max_peers
    has_range = bool(date_from or date_to)

    if refine_query:
        q_text = build_search_query(query, for_news=False)
        q_news = build_search_query(query, for_news=True)
    else:
        q_text = query.strip()
        q_news = query.strip()

    if "site:" not in q_text.lower():
        q_text_br = f"{q_text} site:.br"
    else:
        q_text_br = q_text
    if "site:" not in q_news.lower():
        q_news_br = f"{q_news} site:.br"
    else:
        q_news_br = q_news

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

    try:
        with DDGS() as ddgs:
            # 1) text BR
            for item in ddgs.text(
                q_text_br,
                region="br-pt",
                timelimit=timelimit if has_range else None,
                max_results=limit,
            ) or []:
                _add(item.get("href"))

            # 2) text sem site (mais recall)
            if len(urls) < max(5, limit // 2):
                for item in ddgs.text(
                    q_text,
                    region="br-pt",
                    timelimit=timelimit if has_range else None,
                    max_results=limit,
                ) or []:
                    _add(item.get("href"))

            # 3) news — sempre como complemento (e principal se houver período)
            news_n = limit if has_range else max(6, limit // 2)
            for item in ddgs.news(
                q_news_br,
                region="br-pt",
                timelimit=timelimit if has_range else None,
                max_results=news_n,
            ) or []:
                _add(item.get("url") or item.get("href"))

            if len(urls) < max(4, limit // 3):
                for item in ddgs.news(
                    q_news,
                    region="br-pt",
                    timelimit=timelimit if has_range else None,
                    max_results=news_n,
                ) or []:
                    _add(item.get("url") or item.get("href"))
    except Exception:
        return urls
    return urls[:limit]
