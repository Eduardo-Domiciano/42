from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Article, QueryArticle, TopicQuery
from app.schemas import ArticleOut, TopicQueryOut
from app.services.analyze import build_panorama
from app.services.article_response import build_article_out
from app.services.fetch_article import fetch_and_store_article
from app.services.narrative_summary import build_topic_narrative
from app.services.topic_relevance import (
    filter_and_rank_articles,
    score_topic_relevance,
    topic_tokens,
)
from app.services.web_search import search_news_urls


def _resolve_range(
    date_from: date | None,
    date_to: date | None,
    on_date: date | None,
) -> tuple[date | None, date | None]:
    if on_date:
        return on_date, on_date
    return date_from, date_to


def _in_date_range(
    article: Article,
    date_from: date | None,
    date_to: date | None,
) -> bool:
    if not date_from and not date_to:
        return True
    pub = article.published_at
    if pub is None:
        return not settings.topic_require_published_at_in_range
    d = pub.date()
    if date_from and d < date_from:
        return False
    if date_to and d > date_to:
        return False
    return True


def _local_candidates(
    db: Session,
    topic: str,
    date_from: date | None,
    date_to: date | None,
) -> list[Article]:
    toks = topic_tokens(topic)
    q = select(Article).options(joinedload(Article.source))
    clauses = []

    if toks:
        def _term_clause(term: str):
            like = f"%{term}%"
            return or_(
                Article.title.ilike(like),
                Article.body.ilike(like),
                Article.excerpt.ilike(like),
            )

        # OR no pool (recall); precisão fica com filtro lexical + juiz LLM de contexto
        clauses.append(or_(*[_term_clause(t) for t in toks[:6]]))
    else:
        like = f"%{topic.strip()}%"
        clauses.append(
            or_(
                Article.title.ilike(like),
                Article.body.ilike(like),
                Article.excerpt.ilike(like),
            )
        )

    if date_from:
        clauses.append(Article.published_at >= datetime.combine(date_from, time.min))
    if date_to:
        clauses.append(Article.published_at <= datetime.combine(date_to, time.max))

    pool_limit = max(
        settings.topic_search_max_results * 3,
        settings.topic_search_web_candidates,
    )
    # Sem período: não priorizar só o mais recente no pool local
    if date_from or date_to:
        q = q.where(and_(*clauses)).order_by(Article.published_at.desc()).limit(pool_limit)
    else:
        q = q.where(and_(*clauses)).order_by(Article.id.desc()).limit(pool_limit)
    return list(db.scalars(q).unique().all())


def _article_out(
    db: Session,
    article: Article,
    *,
    allow_llm: bool,
    allow_narrative_llm: bool,
    peer_pool: list[Article],
    themes: list[str] | None = None,
) -> ArticleOut:
    return build_article_out(
        db,
        article,
        allow_llm=allow_llm,
        allow_narrative_llm=allow_narrative_llm,
        run_crossref=settings.crossref_enabled and settings.crossref_on_topic,
        peer_pool=peer_pool,
        themes=themes,
    )


def run_topic_search(
    db: Session,
    topic: str,
    date_from: date | None = None,
    date_to: date | None = None,
    on_date: date | None = None,
    themes: list[str] | None = None,
) -> TopicQueryOut:
    date_from, date_to = _resolve_range(date_from, date_to, on_date)
    topic = topic.strip()

    topic_query = TopicQuery(
        topic_text=topic,
        date_from=date_from,
        date_to=date_to,
        status="running",
    )
    db.add(topic_query)
    db.commit()
    db.refresh(topic_query)

    discarded_relevance = 0
    discarded_date = 0
    candidates: list[Article] = []
    seen_ids: set[int] = set()

    for article in _local_candidates(db, topic, date_from, date_to):
        if article.id in seen_ids:
            continue
        if not _in_date_range(article, date_from, date_to):
            discarded_date += 1
            continue
        seen_ids.add(article.id)
        candidates.append(article)

    web_urls = search_news_urls(
        topic,
        max_results=settings.topic_search_web_candidates,
        date_from=date_from,
        date_to=date_to,
        refine_query=True,
    )
    fetch_failures = 0
    # Para cedo quando já há material relevante suficiente (evita 504 no proxy).
    early_target = max(settings.topic_search_max_results, 8)
    accepted_so_far = sum(
        1 for a in candidates if score_topic_relevance(topic, a).accepted
    )
    for url in web_urls:
        if accepted_so_far >= early_target:
            break
        try:
            article = fetch_and_store_article(db, url)
            article = db.scalar(
                select(Article)
                .options(joinedload(Article.source))
                .where(Article.id == article.id)
            )
            if not article or article.id in seen_ids:
                continue
            if not _in_date_range(article, date_from, date_to):
                discarded_date += 1
                continue
            seen_ids.add(article.id)
            candidates.append(article)
            if score_topic_relevance(topic, article).accepted:
                accepted_so_far += 1
        except Exception:
            fetch_failures += 1
            continue

    ranked, discarded_rel = filter_and_rank_articles(
        topic,
        candidates,
        limit=settings.topic_search_max_results,
    )
    discarded_relevance = discarded_rel

    collected: list[Article] = []
    for rank, (article, rel) in enumerate(ranked):
        collected.append(article)
        db.add(
            QueryArticle(
                topic_query_id=topic_query.id,
                article_id=article.id,
                rank=rank,
                discovery_method=f"relevance:{rel.score:.2f}",
            )
        )

    outs: list[ArticleOut] = []
    claims_map = {}
    xrefs_map = {}
    for idx, article in enumerate(collected):
        # Particiona LLM: claims e resumo humano só nos primeiros N (um de cada vez via lock)
        allow_llm = idx < settings.claim_llm_max_per_topic
        allow_narrative_llm = idx < settings.narrative_llm_max_per_topic
        out = _article_out(
            db,
            article,
            allow_llm=allow_llm,
            allow_narrative_llm=allow_narrative_llm,
            peer_pool=collected,
            themes=themes,
        )
        outs.append(out)
        claims_map[article.id] = out.claims
        xrefs_map[article.id] = out.cross_references

    panorama = build_panorama(
        collected,
        article_claims=claims_map,
        article_xrefs=xrefs_map,
        discarded_relevance=discarded_relevance,
        discarded_date=discarded_date,
        candidates_considered=len(candidates),
    )
    topic_query.status = "completed"
    topic_query.summary = (
        f"{len(collected)} artigo(s) relevantes para “{topic}”"
        + (f" entre {date_from} e {date_to}" if date_from or date_to else "")
        + f" · {len(web_urls)} URL(s) web, {len(candidates)} candidato(s)"
        + f", {discarded_relevance} fora do tema"
        + (f", {discarded_date} fora do período" if discarded_date else "")
        + (f", {fetch_failures} falha(s) de fetch" if fetch_failures else "")
        + f" · {panorama.total_claims} claim(s)"
        + f" · {panorama.total_cross_refs} cruzamento(s)"
    )
    db.commit()

    return TopicQueryOut(
        id=topic_query.id,
        topic_text=topic_query.topic_text,
        date_from=topic_query.date_from,
        date_to=topic_query.date_to,
        status=topic_query.status,
        summary=topic_query.summary,
        created_at=topic_query.created_at,
        articles=outs,
        panorama=panorama,
        narrative_summary=build_topic_narrative(
            topic=topic_query.topic_text,
            panorama=panorama,
            articles_count=len(outs),
        ),
    )
