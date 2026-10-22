from __future__ import annotations

import hashlib
import re
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import httpx
import trafilatura
from dateutil import parser as date_parser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, Source
from app.services.content_classifier import classify_content


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def resolve_source(db: Session, url: str) -> Source | None:
    domain = _domain_of(url)
    sources = db.scalars(select(Source)).all()
    for source in sources:
        if source.domain and (
            domain == source.domain or domain.endswith("." + source.domain)
        ):
            return source
    return None


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None


def fetch_and_store_article(db: Session, url: str) -> Article:
    normalized = normalize_url(str(url))
    existing = db.scalar(select(Article).where(Article.normalized_url == normalized))
    if existing and existing.body:
        return existing

    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(
        follow_redirects=True,
        timeout=settings.http_timeout_seconds,
        headers=headers,
    ) as client:
        response = client.get(normalized)
        response.raise_for_status()
        html = response.text

    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        output_format="json",
        url=normalized,
    )
    meta = trafilatura.extract_metadata(html) if html else None

    title = None
    author = None
    body = None
    published_at = None

    if extracted:
        import json

        try:
            payload = json.loads(extracted)
            title = payload.get("title")
            author = payload.get("author")
            body = payload.get("text")
            published_at = _parse_published(payload.get("date"))
        except json.JSONDecodeError:
            body = extracted

    if meta:
        title = title or getattr(meta, "title", None)
        author = author or getattr(meta, "author", None)
        published_at = published_at or _parse_published(getattr(meta, "date", None))

    if not body:
        # Fallback mínimo: texto limpo sem tags
        body = re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body).strip()[:8000]

    excerpt = (body[:400] + "…") if body and len(body) > 400 else body
    content_hash = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    source = resolve_source(db, normalized)

    if existing:
        existing.title = title or existing.title
        existing.author = author or existing.author
        existing.body = body
        existing.excerpt = excerpt
        existing.published_at = published_at or existing.published_at
        existing.content_hash = content_hash
        existing.source_id = source.id if source else existing.source_id
        existing.fetched_at = datetime.utcnow()
        db.flush()
        existing.content_type = classify_content(existing).content_type
        db.commit()
        db.refresh(existing)
        return existing

    article = Article(
        url=str(url),
        normalized_url=normalized,
        title=title,
        author=author,
        body=body,
        excerpt=excerpt,
        published_at=published_at,
        content_hash=content_hash,
        source_id=source.id if source else None,
        content_type="article",
    )
    db.add(article)
    db.flush()
    article.content_type = classify_content(article).content_type
    db.commit()
    db.refresh(article)
    return article
