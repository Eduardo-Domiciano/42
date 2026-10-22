"""Monta ArticleOut usando acervo (snapshot) quando possível."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article
from app.schemas import ArticleOut, SourceOut
from app.services.analysis_cache import (
    get_matching_snapshot,
    invalidate_snapshots,
    list_outbound_links,
    save_snapshot,
    snapshot_to_analysis_out,
)
from app.services.analyze import analyze_article
from app.services.claim_pipeline import ensure_claim_assessments
from app.services.cross_reference import run_cross_reference_for_article
from app.services.narrative_summary import build_article_narrative


def build_article_out(
    db: Session,
    article: Article,
    *,
    run_claims: bool = True,
    allow_llm: bool = True,
    run_crossref: bool = True,
    peer_pool: list[Article] | None = None,
    force: bool = False,
) -> ArticleOut:
    claims = []
    if run_claims:
        claims = ensure_claim_assessments(
            db, article, allow_llm=allow_llm, force=force
        )

    xrefs = []
    if run_crossref and settings.crossref_enabled and claims:
        limited = claims[: settings.crossref_max_claims_url]
        xrefs = run_cross_reference_for_article(
            db,
            article,
            limited,
            peer_pool=peer_pool,
            allow_llm_stance=False,
            force=force,
        )

    body = article.body or ""
    preview = (body[:500] + "…") if len(body) > 500 else body or None
    source_out = SourceOut.model_validate(article.source) if article.source else None
    outbound = list_outbound_links(db, article.id)

    snap = None if force else get_matching_snapshot(db, article)
    if snap:
        analysis = snapshot_to_analysis_out(snap)
        narrative = snap.narrative_summary or ""
        cached = True
    else:
        if force:
            invalidate_snapshots(db, article.id)
        analysis = analyze_article(article, claims=claims)
        narrative = build_article_narrative(
            title=article.title,
            source=source_out,
            analysis=analysis,
            claims=claims,
            cross_references=xrefs,
        )
        save_snapshot(db, article, analysis, narrative, replace_all=force)
        cached = False

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
        analysis_cached=cached,
        outbound_links=outbound,
    )
