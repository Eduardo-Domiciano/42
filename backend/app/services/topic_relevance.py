"""Relevância tema × artigo: tokenização, frase e score lexical (+ embeddings opcionais)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from math import ceil

from app.config import settings
from app.models import Article
from app.services.nn_embeddings import semantic_similarity

_STOP = {
    "sobre",
    "para",
    "como",
    "mais",
    "menos",
    "apos",
    "antes",
    "ainda",
    "tambem",
    "pelo",
    "pela",
    "pelos",
    "pelas",
    "dos",
    "das",
    "uma",
    "uns",
    "este",
    "esta",
    "isso",
    "aquele",
    "aquela",
    "segundo",
    "conforme",
    "entre",
    "desde",
    "quando",
    "onde",
    "qual",
    "quais",
    "que",
    "com",
    "sem",
    "por",
    "nao",
    "sim",
    "the",
    "and",
    "for",
    "noticia",
    "noticias",
    "brasil",
    "anos",
    "ano",
    "hoje",
    "ontem",
}


@dataclass
class RelevanceResult:
    score: float
    lexical: float
    semantic: float | None
    token_hits: int
    tokens: list[str]
    accepted: bool
    reason: str


def fold_text(text: str) -> str:
    """Minúsculas + remove acentos (tributária → tributaria)."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def topic_tokens(topic: str) -> list[str]:
    raw = [t for t in re.findall(r"\w+", fold_text(topic)) if len(t) >= 3]
    toks = [t for t in raw if t not in _STOP and not t.isdigit()]
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]


def topic_phrase(topic: str) -> str:
    toks = topic_tokens(topic)
    if toks:
        return " ".join(toks[:6])
    return fold_text(topic).strip()


def build_search_query(topic: str, *, for_news: bool = False) -> str:
    """Query focada sem aspas rígidas (aspas zeravam resultados no DDG)."""
    phrase = topic_phrase(topic)
    toks = topic_tokens(topic)
    if not phrase:
        base = (topic or "").strip()
    elif len(toks) <= 2:
        base = phrase
    else:
        base = " ".join(toks[:5])
    if for_news:
        return f"{base} noticia"
    return base


def _blob_for_article(article: Article) -> tuple[str, str, str]:
    title = fold_text(article.title or "")
    excerpt = fold_text(article.excerpt or "")
    body = fold_text((article.body or "")[:2500])
    return title, excerpt, body


def _token_hit(token: str, text: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text))


def lexical_topic_score(
    topic: str, article: Article
) -> tuple[float, int, int, bool, list[str]]:
    toks = topic_tokens(topic)
    if not toks:
        return 0.0, 0, 0, False, []
    title, excerpt, body = _blob_for_article(article)
    phrase = topic_phrase(topic)

    hits_title = sum(1 for t in toks if _token_hit(t, title))
    hits_excerpt = sum(1 for t in toks if _token_hit(t, excerpt))
    hits_body = sum(1 for t in toks if _token_hit(t, body))
    hits_any = sum(
        1
        for t in toks
        if _token_hit(t, title) or _token_hit(t, excerpt) or _token_hit(t, body)
    )
    phrase_hit = bool(phrase) and (
        phrase in title or phrase in excerpt or phrase in body[:800]
    )

    n = len(toks)
    score = (
        0.55 * (hits_title / n)
        + 0.25 * (hits_excerpt / n)
        + 0.20 * (hits_body / n)
    )
    if phrase_hit:
        score = min(1.0, score + 0.22)
    elif hits_title == n:
        score = min(1.0, score + 0.1)
    return max(0.0, min(1.0, score)), hits_any, hits_title, phrase_hit, toks


def score_topic_relevance(topic: str, article: Article) -> RelevanceResult:
    lexical, hits, title_hits, phrase_hit, toks = lexical_topic_score(topic, article)
    title = article.title or ""
    excerpt = article.excerpt or ""
    body = (article.body or "")[:800]
    blob = f"{title}\n{excerpt}\n{body}".strip()
    semantic = semantic_similarity(topic, blob) if blob else None

    if semantic is not None:
        score = 0.65 * lexical + 0.35 * semantic
    else:
        score = lexical

    min_score = settings.topic_min_relevance
    n = max(len(toks), 1)
    need_hits = 1 if n == 1 else max(2, ceil(n * 0.5))

    if not toks:
        accepted = False
        reason = "tema sem tokens úteis"
    elif phrase_hit and lexical >= 0.25:
        accepted = True
        reason = "frase do tema no texto"
    elif title_hits >= need_hits and lexical >= min_score * 0.8:
        accepted = True
        reason = f"tokens no título ({title_hits}/{n})"
    elif hits >= need_hits and title_hits >= 1 and lexical >= min_score * 0.85:
        accepted = score >= min_score * 0.85
        reason = f"overlap com título ({hits}/{n})"
    elif hits >= need_hits and lexical >= min_score:
        accepted = score >= min_score
        reason = f"overlap lexical ({hits}/{n})"
    elif (
        semantic is not None
        and semantic >= settings.topic_min_semantic
        and lexical >= settings.topic_min_lexical_for_semantic
        and hits >= max(1, need_hits - 1)
    ):
        accepted = score >= min_score * 0.85
        reason = f"semântico+lexical ({semantic:.2f})"
    else:
        accepted = False
        reason = (
            f"fora do tema (score={score:.2f}, lexical={lexical:.2f}, "
            f"hits={hits}/{n}, título={title_hits})"
        )

    return RelevanceResult(
        score=round(score, 3),
        lexical=round(lexical, 3),
        semantic=round(semantic, 3) if semantic is not None else None,
        token_hits=hits,
        tokens=toks,
        accepted=accepted,
        reason=reason,
    )


def filter_and_rank_articles(
    topic: str,
    articles: list[Article],
    *,
    limit: int,
) -> tuple[list[tuple[Article, RelevanceResult]], int]:
    scored: list[tuple[Article, RelevanceResult]] = []
    rejected: list[tuple[Article, RelevanceResult]] = []
    for art in articles:
        rel = score_topic_relevance(topic, art)
        if rel.accepted:
            scored.append((art, rel))
        else:
            rejected.append((art, rel))
    scored.sort(key=lambda x: (x[1].score, x[1].lexical), reverse=True)

    # Fallback: se o filtro zerar tudo, mantém os melhores com pelo menos 1 token
    if not scored and rejected:
        soft_floor = max(0.18, settings.topic_min_relevance * 0.45)
        soft = [
            (a, r)
            for a, r in rejected
            if r.score >= soft_floor and r.token_hits >= 1
        ]
        soft.sort(key=lambda x: (x[1].score, x[1].lexical), reverse=True)
        if soft:
            kept = soft[:limit]
            return kept, len(rejected) - len(kept)

    return scored[:limit], len(rejected)
