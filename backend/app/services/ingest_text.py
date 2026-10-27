"""Ingestão de texto colado (sem URL) para o mesmo pipeline de análise."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article
from app.services.content_classifier import classify_content


def _normalize_body(text: str) -> str:
    body = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def _synthetic_url(content_hash: str) -> str:
    return f"text://pasted/{content_hash}"


def store_pasted_text(
    db: Session,
    *,
    text: str,
    title: str | None = None,
    published_at: date | None = None,
) -> Article:
    body = _normalize_body(text)
    if len(body) < 80:
        raise ValueError("Texto muito curto (mínimo cerca de 80 caracteres).")
    if len(body) > 100_000:
        raise ValueError("Texto muito longo (máximo 100.000 caracteres).")

    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    url = _synthetic_url(content_hash)
    clean_title = (title or "").strip() or None
    if clean_title and len(clean_title) > 400:
        clean_title = clean_title[:397] + "…"

    published_dt = (
        datetime.combine(published_at, time.min) if published_at else None
    )

    existing = db.scalar(
        select(Article).where(Article.normalized_url == url)
    )
    excerpt = (body[:400] + "…") if len(body) > 400 else body

    if existing:
        existing.title = clean_title or existing.title
        existing.body = body
        existing.excerpt = excerpt
        existing.content_hash = content_hash
        existing.fetched_at = datetime.utcnow()
        if published_dt is not None:
            existing.published_at = published_dt
        if not existing.title:
            # Primeira linha como título de fallback
            first = body.split("\n", 1)[0].strip()
            existing.title = first[:200] if first else "Texto colado"
        db.flush()
        existing.content_type = classify_content(existing).content_type
        db.commit()
        db.refresh(existing)
        return existing

    fallback_title = clean_title
    if not fallback_title:
        first = body.split("\n", 1)[0].strip()
        fallback_title = first[:200] if first else "Texto colado"

    article = Article(
        url=url,
        normalized_url=url,
        title=fallback_title,
        author=None,
        body=body,
        excerpt=excerpt,
        published_at=published_dt,
        content_hash=content_hash,
        content_type="article",
        source_id=None,
        fetched_at=datetime.utcnow(),
    )
    db.add(article)
    db.flush()
    article.content_type = classify_content(article).content_type
    db.commit()
    db.refresh(article)
    return article
