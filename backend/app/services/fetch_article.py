from __future__ import annotations

import hashlib
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
import trafilatura
from dateutil import parser as date_parser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, Source
from app.services.analysis_cache import replace_outbound_links
from app.services.content_classifier import classify_content

_HREF = re.compile(
    r"""<a\s+[^>]*href=["']([^"'#]+)["'][^>]*>(.*?)</a>""",
    re.I | re.DOTALL,
)


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


def extract_outbound_links(
    html: str, *, base_url: str, limit: int = 40
) -> list[tuple[str, str | None]]:
    """Extrai hrefs absolutos do HTML (citações / fontes no texto)."""
    out: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    base_norm = normalize_url(base_url)
    for match in _HREF.finditer(html or ""):
        raw = unescape(match.group(1).strip())
        if raw.startswith(("javascript:", "mailto:", "tel:", "data:")):
            continue
        abs_url = urljoin(base_url, raw)
        if not abs_url.startswith(("http://", "https://")):
            continue
        try:
            nurl = normalize_url(abs_url)
        except Exception:
            continue
        if nurl == base_norm or nurl in seen:
            continue
        seen.add(nurl)
        anchor = re.sub(r"<[^>]+>", " ", match.group(2) or "")
        anchor = re.sub(r"\s+", " ", unescape(anchor)).strip() or None
        out.append((abs_url, anchor))
        if len(out) >= limit:
            break
    return out


def fetch_and_store_article(
    db: Session, url: str, *, refresh: bool = False
) -> Article:
    normalized = normalize_url(str(url))
    existing = db.scalar(select(Article).where(Article.normalized_url == normalized))
    if existing and existing.body and not refresh:
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
        body = re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body).strip()[:8000]

    excerpt = (body[:400] + "…") if body and len(body) > 400 else body
    content_hash = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    source = resolve_source(db, normalized)
    outbound = extract_outbound_links(html, base_url=normalized)

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
        replace_outbound_links(db, existing.id, outbound)
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
    replace_outbound_links(db, article.id, outbound)
    return article
