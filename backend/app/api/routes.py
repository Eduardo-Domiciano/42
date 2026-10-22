from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db import get_db
from app.models import Article, TopicQuery
from app.schemas import (
    ArticleOut,
    IngestUrlRequest,
    SourceOut,
    TopicQueryOut,
    TopicSearchRequest,
)
from app.services.analyze import analyze_article, build_panorama
from app.services.claim_pipeline import ensure_claim_assessments
from app.services.cross_reference import run_cross_reference_for_article
from app.services.fetch_article import fetch_and_store_article
from app.services.llm_client import llm_configured
from app.services.narrative_summary import build_article_narrative, build_topic_narrative
from app.services.topic_search import run_topic_search

router = APIRouter(prefix="/api")


def _article_out(
    db: Session,
    article: Article,
    *,
    run_claims: bool = True,
    allow_llm: bool = True,
    run_crossref: bool = True,
    peer_pool: list[Article] | None = None,
) -> ArticleOut:
    claims = []
    if run_claims:
        claims = ensure_claim_assessments(db, article, allow_llm=allow_llm)
    analysis = analyze_article(article, claims=claims)

    xrefs = []
    if run_crossref and settings.crossref_enabled and claims:
        limited = claims[: settings.crossref_max_claims_url]
        xrefs = run_cross_reference_for_article(
            db,
            article,
            limited,
            peer_pool=peer_pool,
            allow_llm_stance=False,
        )

    body = article.body or ""
    preview = (body[:500] + "…") if len(body) > 500 else body or None
    source_out = SourceOut.model_validate(article.source) if article.source else None
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


@router.get("/health")
def health() -> dict[str, object]:
    from app.services.nn_runtime import nli_status

    return {
        "status": "ok",
        "llm_configured": llm_configured(),
        "claim_use_llm": settings.claim_use_llm,
        "crossref_enabled": settings.crossref_enabled,
        "nn": nli_status(),
    }


@router.get("/catalog/bias")
def get_bias_catalog() -> dict:
    from app.services.bias_catalog import load_bias_catalog

    catalog = load_bias_catalog()
    return {
        "version": catalog.get("version"),
        "country": catalog.get("country"),
        "updated_at": catalog.get("updated_at"),
        "methodology": catalog.get("methodology"),
        "sources": catalog.get("sources") or {},
    }


@router.post("/ingest/url", response_model=ArticleOut)
def ingest_url(payload: IngestUrlRequest, db: Session = Depends(get_db)) -> ArticleOut:
    try:
        article = fetch_and_store_article(db, str(payload.url))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Falha ao buscar URL: {exc}") from exc

    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article.id)
    )
    if not article:
        raise HTTPException(status_code=500, detail="Artigo não persistido")
    return _article_out(db, article, allow_llm=True, run_crossref=True)


@router.post("/search/topic", response_model=TopicQueryOut)
def search_topic(
    payload: TopicSearchRequest, db: Session = Depends(get_db)
) -> TopicQueryOut:
    if payload.date_from and payload.date_to and payload.date_from > payload.date_to:
        raise HTTPException(status_code=400, detail="date_from não pode ser após date_to")
    return run_topic_search(
        db,
        topic=payload.topic,
        date_from=payload.date_from,
        date_to=payload.date_to,
        on_date=payload.on_date,
    )


@router.get("/topic-queries/{query_id}", response_model=TopicQueryOut)
def get_topic_query(query_id: int, db: Session = Depends(get_db)) -> TopicQueryOut:
    from app.models import QueryArticle

    topic_query = db.scalar(select(TopicQuery).where(TopicQuery.id == query_id))
    if not topic_query:
        raise HTTPException(status_code=404, detail="Consulta não encontrada")

    articles = list(
        db.scalars(
            select(Article)
            .options(joinedload(Article.source))
            .join(QueryArticle, QueryArticle.article_id == Article.id)
            .where(QueryArticle.topic_query_id == query_id)
            .order_by(QueryArticle.rank)
        )
        .unique()
        .all()
    )
    outs = []
    claims_map = {}
    xrefs_map = {}
    for idx, article in enumerate(articles):
        allow_llm = idx < settings.claim_llm_max_per_topic
        out = _article_out(
            db,
            article,
            allow_llm=allow_llm,
            run_crossref=settings.crossref_on_topic,
            peer_pool=articles,
        )
        outs.append(out)
        claims_map[article.id] = out.claims
        xrefs_map[article.id] = out.cross_references

    panorama = build_panorama(
        articles, article_claims=claims_map, article_xrefs=xrefs_map
    )
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


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(article_id: int, db: Session = Depends(get_db)) -> ArticleOut:
    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    return _article_out(db, article)


@router.post("/articles/{article_id}/reanalyze", response_model=ArticleOut)
def reanalyze_article(article_id: int, db: Session = Depends(get_db)) -> ArticleOut:
    article = db.scalar(
        select(Article)
        .options(joinedload(Article.source))
        .where(Article.id == article_id)
    )
    if not article:
        raise HTTPException(status_code=404, detail="Artigo não encontrado")
    claims = ensure_claim_assessments(db, article, force=True, allow_llm=True)
    run_cross_reference_for_article(
        db, article, claims[: settings.crossref_max_claims_url], force=True
    )
    return _article_out(db, article, run_claims=True, run_crossref=True)
