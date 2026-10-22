"""Persistência e leitura do snapshot de análise (acervo SQLite)."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, ArticleAnalysis, ArticleOutboundLink
from app.schemas import ArticleAnalysisOut, OutboundLinkOut
from app.services.llm_client import llm_configured
from app.services.nn_runtime import nn_packages_installed


def _config_note() -> str:
    parts = []
    if llm_configured() and settings.claim_use_llm:
        parts.append("llm")
    if settings.nn_enabled and nn_packages_installed():
        parts.append("nn")
    return "+".join(parts) or "heuristic"


def get_matching_snapshot(
    db: Session, article: Article
) -> ArticleAnalysis | None:
    if not article.content_hash:
        return None
    return db.scalar(
        select(ArticleAnalysis)
        .where(
            ArticleAnalysis.article_id == article.id,
            ArticleAnalysis.content_hash == article.content_hash,
        )
        .order_by(ArticleAnalysis.created_at.desc())
    )


def snapshot_to_analysis_out(snap: ArticleAnalysis) -> ArticleAnalysisOut:
    factors: list[str] = []
    try:
        factors = json.loads(snap.factors_json or "[]")
    except json.JSONDecodeError:
        factors = []
    return ArticleAnalysisOut(
        content_type_guess=snap.content_type_guess,
        content_type_confidence=snap.content_type_confidence,
        authority_tier=snap.authority_tier,
        bias_label=snap.bias_label,
        bias_score=snap.bias_score,
        bias_catalog_version=snap.bias_catalog_version,
        ownership_name=snap.ownership_name or "desconhecido",
        source_partiality_note=snap.source_partiality_note,
        temporal_coherence=snap.temporal_coherence,
        preliminary_verdict=snap.preliminary_verdict,
        analysis_method=snap.analysis_method,
        factors=factors,
    )


def invalidate_snapshots(db: Session, article_id: int) -> None:
    for old in list(
        db.scalars(
            select(ArticleAnalysis).where(ArticleAnalysis.article_id == article_id)
        ).all()
    ):
        db.delete(old)
    db.flush()


def save_snapshot(
    db: Session,
    article: Article,
    analysis: ArticleAnalysisOut,
    narrative: str,
    *,
    replace_all: bool = False,
) -> ArticleAnalysis:
    ownership = analysis.ownership_name or (
        (article.source.ownership_name or article.source.ownership_group)
        if article.source
        else None
    ) or "desconhecido"

    existing = None if replace_all else get_matching_snapshot(db, article)
    if existing:
        snap = existing
    else:
        invalidate_snapshots(db, article.id)
        snap = ArticleAnalysis(article_id=article.id)
        db.add(snap)

    snap.content_hash = article.content_hash or ""
    snap.preliminary_verdict = analysis.preliminary_verdict
    snap.analysis_method = analysis.analysis_method
    snap.temporal_coherence = analysis.temporal_coherence
    snap.source_partiality_note = analysis.source_partiality_note
    snap.factors_json = json.dumps(analysis.factors, ensure_ascii=False)
    snap.narrative_summary = narrative or ""
    snap.ownership_name = ownership
    snap.bias_label = analysis.bias_label
    snap.bias_score = analysis.bias_score
    snap.bias_catalog_version = analysis.bias_catalog_version
    snap.authority_tier = analysis.authority_tier
    snap.content_type_guess = analysis.content_type_guess
    snap.content_type_confidence = analysis.content_type_confidence
    snap.author = article.author
    snap.title = article.title
    snap.url = article.url
    snap.published_at = article.published_at
    snap.config_note = _config_note()
    snap.created_at = datetime.utcnow()
    db.commit()
    db.refresh(snap)
    return snap


def list_outbound_links(db: Session, article_id: int) -> list[OutboundLinkOut]:
    rows = list(
        db.scalars(
            select(ArticleOutboundLink)
            .where(ArticleOutboundLink.article_id == article_id)
            .order_by(ArticleOutboundLink.id)
        ).all()
    )
    return [
        OutboundLinkOut(id=r.id, url=r.url, anchor_text=r.anchor_text) for r in rows
    ]


def replace_outbound_links(
    db: Session,
    article_id: int,
    links: list[tuple[str, str | None]],
) -> None:
    for old in list(
        db.scalars(
            select(ArticleOutboundLink).where(
                ArticleOutboundLink.article_id == article_id
            )
        ).all()
    ):
        db.delete(old)
    db.flush()
    seen: set[str] = set()
    for url, anchor in links:
        if not url or url in seen:
            continue
        seen.add(url)
        db.add(
            ArticleOutboundLink(
                article_id=article_id,
                url=url[:2000],
                anchor_text=(anchor[:500] if anchor else None),
            )
        )
    db.commit()
