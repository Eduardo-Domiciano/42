"""Localiza artigo já analisado no acervo (URL, hash do texto ou título + data)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, ArticleAnalysis
from app.schemas import ArticleLookupHit, ArticleLookupResponse
from app.services.fetch_article import normalize_url
from app.services.ingest_text import _normalize_body


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _title_key(title: str | None) -> str:
    t = _fold(title or "")
    t = re.sub(r"\s+", " ", t)
    return t


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min)
    end = datetime.combine(d, time.max)
    return start, end


def _latest_analysis(
    db: Session, article_id: int
) -> ArticleAnalysis | None:
    return db.scalar(
        select(ArticleAnalysis)
        .where(ArticleAnalysis.article_id == article_id)
        .order_by(ArticleAnalysis.created_at.desc())
        .limit(1)
    )


def _hit(
    article: Article, snap: ArticleAnalysis, matched_by: str
) -> ArticleLookupHit:
    return ArticleLookupHit(
        article_id=article.id,
        title=article.title or snap.title,
        url=article.url,
        published_at=article.published_at,
        analyzed_at=snap.created_at,
        fetched_at=article.fetched_at,
        matched_by=matched_by,
        has_analysis=True,
    )


def _filter_by_published_day(
    articles: list[Article], published_at: date | None
) -> list[Article]:
    if not published_at:
        return articles
    start, end = _day_bounds(published_at)
    return [
        a
        for a in articles
        if a.published_at is not None and start <= a.published_at <= end
    ]


def lookup_prior_analysis(
    db: Session,
    *,
    url: str | None = None,
    title: str | None = None,
    text: str | None = None,
    published_at: date | None = None,
) -> ArticleLookupResponse:
    """
    Procura artigo que já tem snapshot de análise.
    Ordem: URL normalizada → hash do texto → título (com data se informada).
    """
    url_s = (url or "").strip() or None
    title_s = (title or "").strip() or None
    text_s = (text or "").strip() or None

    if not url_s and not title_s and not text_s:
        return ArticleLookupResponse(found=False)

    # 1) URL
    if url_s:
        try:
            nurl = normalize_url(url_s)
        except Exception:
            nurl = url_s
        article = db.scalar(
            select(Article).where(Article.normalized_url == nurl)
        )
        if article:
            if published_at and not _filter_by_published_day([article], published_at):
                pass
            else:
                snap = _latest_analysis(db, article.id)
                if snap:
                    return ArticleLookupResponse(
                        found=True, match=_hit(article, snap, "url")
                    )

    # 2) Texto (mesmo hash do ingest colado)
    if text_s and len(text_s) >= 80:
        body = _normalize_body(text_s)
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        candidates = list(
            db.scalars(
                select(Article)
                .where(Article.content_hash == content_hash)
                .order_by(Article.fetched_at.desc())
                .limit(20)
            ).all()
        )
        candidates = _filter_by_published_day(candidates, published_at)
        for article in candidates:
            snap = _latest_analysis(db, article.id)
            if snap:
                return ArticleLookupResponse(
                    found=True, match=_hit(article, snap, "text")
                )

    # 3) Título (+ data de publicação, se houver)
    if title_s and len(title_s) >= 8:
        key = _title_key(title_s)
        # SQLite: comparação case-insensitive aproximada via lower
        q = select(Article).where(
            func.lower(func.trim(Article.title)) == title_s.lower().strip()
        )
        if published_at:
            start, end = _day_bounds(published_at)
            q = q.where(
                Article.published_at.is_not(None),
                Article.published_at >= start,
                Article.published_at <= end,
            )
        q = q.order_by(Article.fetched_at.desc()).limit(30)
        for article in db.scalars(q).all():
            if _title_key(article.title) != key:
                continue
            snap = _latest_analysis(db, article.id)
            if snap:
                return ArticleLookupResponse(
                    found=True, match=_hit(article, snap, "title")
                )

    return ArticleLookupResponse(found=False)
