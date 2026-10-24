from __future__ import annotations

from urllib.parse import urlparse

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PROFILES_PATH
from app.models import Source
from app.services.bias_catalog import (
    bias_for_slug,
    catalog_version,
    load_bias_catalog,
    ownership_display,
)


def _normalize_host(host: str) -> str:
    return host.lower().removeprefix("www.").strip()


def _host_list(host_patterns: list[str] | None) -> list[str]:
    if not host_patterns:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in host_patterns:
        if not isinstance(raw, str) or not raw.strip():
            continue
        host = _normalize_host(raw)
        if host and host not in seen:
            seen.add(host)
            out.append(host)
    return out


def _primary_domain(host_patterns: list[str] | None) -> str | None:
    hosts = _host_list(host_patterns)
    return hosts[0] if hosts else None


def _topics_csv(topics: list | str | None) -> str | None:
    if topics is None:
        return None
    if isinstance(topics, str):
        parts = [p.strip().lower() for p in topics.split(",") if p.strip()]
    else:
        parts = [str(p).strip().lower() for p in topics if str(p).strip()]
    if not parts:
        return None
    return ",".join(parts)


def seed_brazil_sources(db: Session) -> int:
    if not PROFILES_PATH.exists():
        return 0

    load_bias_catalog.cache_clear()
    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8")) or {}
    brazil = data.get("brazil") or {}
    version = catalog_version()
    created = 0

    for slug, profile in brazil.items():
        if not isinstance(profile, dict):
            continue
        existing = db.scalar(select(Source).where(Source.slug == slug))
        hosts = _host_list(profile.get("host_patterns"))
        domain = hosts[0] if hosts else None
        homepage = profile.get("homepage_url")
        if not domain and homepage:
            domain = _normalize_host(urlparse(homepage).netloc)

        independence = profile.get("independence_group")
        bias = bias_for_slug(slug)

        payload = dict(
            name=profile.get("name") or slug,
            domain=domain,
            kind=profile.get("source_kind"),
            source_role=profile.get("source_role"),
            authority_tier=profile.get("authority_tier"),
            authority_score=profile.get("authority_score"),
            ownership_group=independence,
            ownership_name=ownership_display(slug, independence),
            bias_score=bias.get("bias_score"),
            bias_label=bias.get("bias_label"),
            bias_note=bias.get("note"),
            bias_catalog_version=version,
            country=profile.get("audience_country") or "BR",
            topics=_topics_csv(profile.get("topics")),
            host_patterns=",".join(hosts) if hosts else None,
            notes=profile.get("notes"),
        )

        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            db.add(Source(slug=slug, **payload))
            created += 1

    db.commit()
    return created
