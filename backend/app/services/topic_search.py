from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Article, QueryArticle, TopicQuery
from app.schemas import ArticleOut, SourceOut, TopicQueryOut
from app.services.analyze import analyze_article, build_panorama
from app.services.claim_pipeline import ensure_claim_assessments
from app.services.cross_reference import run_cross_reference_for_article
from app.services.fetch_article import fetch_and_store_article
from app.services.narrative_summary import build_article_narrative, build_topic_narrative
from app.services.topic_relevance import filter_and_rank_articles, topic_tokens
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
        # OR no banco (recall); o filtro de relevância corta ruído depois
        like_clauses = []
        for term in toks[:6]:
            like = f"%{term}%"
            like_clauses.append(
                or_(
                    Article.title.ilike(like),
                    Article.body.ilike(like),
                    Article.excerpt.ilike(like),
                )
            )
        clauses.append(or_(*like_clauses))
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
    peer_pool: list[Article],
) -> ArticleOut:
    claims = ensure_claim_assessments(db, article, allow_llm=allow_llm)
    xrefs = []
    if settings.crossref_enabled and settings.crossref_on_topic and claims:
        xrefs = run_cross_reference_for_article(
            db,
            article,
            claims[: settings.crossref_max_claims_url],
            peer_pool=peer_pool,
            allow_llm_stance=False,
        )
    body = article.body or ""
    preview = (body[:500] + "…") if len(body) > 500 else body or None
    source_out = SourceOut.model_validate(article.source) if article.source else None
    analysis = analyze_article(article, claims=claims)
    narrative = build_article_narrative(
        title=article.title,
        source=source_out,
        analysis=analysis,
        claims=claims,
        cross_references=xrefs,
    )
    return ArticleOut(
        id=article.id,
        url=article.url,
        title=article.title,
        author=article.author,
        excerpt=article.excerpt,
        body_preview=preview,
        published_at=article.published_at,
        content_type=article.content_type,
        source=source_out,
        analysis=analysis,
        claims=claims,
        cross_references=xrefs,
        narrative_summary=narrative,
    )


def run_topic_search(
    db: Session,
    topic: str,
    date_from: date | None = None,
    date_to: date | None = None,
    on_date: date | None = None,
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
    for url in web_urls:
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
        allow_llm = idx < settings.claim_llm_max_per_topic
        out = _article_out(
            db, article, allow_llm=allow_llm, peer_pool=collected
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
