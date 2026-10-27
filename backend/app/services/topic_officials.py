"""Temas oficiais → domínios primary para busca F4 (site:…)."""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Source

# Lexicon PT curto: palavra/radical → tema do catálogo.
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "economia": (
        "economia",
        "economico",
        "economica",
        "inflacao",
        "ipca",
        "igpm",
        "selic",
        "juros",
        "pib",
        "cambio",
        "dolar",
        "fiscal",
        "orcamento",
        "divida",
        "tesouro",
        "fazenda",
        "tributo",
        "tributos",
        "imposto",
        "impostos",
        "receita federal",
        "banco central",
        "bcb",
        "cvm",
        "bolsa",
        "acoes",
        "mercado de capitais",
        "gasto publico",
        "despesa",
        "arrecadacao",
        "deficit",
        "superavit",
        "emprego",
        "desemprego",
        "caged",
        "salario",
        "renda",
    ),
    "saude": (
        "saude",
        "sus",
        "anvisa",
        "vacina",
        "hospitais",
        "hospital",
        "epidemia",
        "pandemia",
        "mortalidade",
        "datasus",
    ),
    "educacao": (
        "educacao",
        "enem",
        "ideb",
        "inep",
        "escola",
        "censo escolar",
        "universidade",
    ),
    "demografia": (
        "demografia",
        "censo",
        "populacao",
        "habitantes",
        "natalidade",
    ),
    "governo": (
        "governo",
        "diario oficial",
        "portaria",
        "decreto",
        "transparencia",
        "licitacao",
        "tcu",
        "cgu",
    ),
}

_FALLBACK_SITES = ("gov.br", "ibge.gov.br", "bcb.gov.br")


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def detect_topics(text: str) -> list[str]:
    """Detecta temas a partir do texto do claim (lexicon)."""
    folded = _fold(text)
    found: list[str] = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in folded:
                found.append(topic)
                break
    return found


def _parse_topics(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def _source_search_domain(source: Source) -> str | None:
    """Um host por fonte para site: (domain principal; evita encher a query)."""
    host = (source.domain or "").lower().removeprefix("www.").strip()
    if not host or host == "gov.br":
        return None
    return host


def official_domains_for_topics(db: Session, topics: list[str]) -> list[str]:
    """Domínios primary cujo topics intersecta a lista pedida (1 por fonte)."""
    if not topics:
        return []
    wanted = {t.lower() for t in topics}
    sources = list(
        db.scalars(select(Source).where(Source.authority_tier == "primary")).all()
    )
    sources.sort(
        key=lambda s: (-(s.authority_score or 0.0), s.slug or ""),
    )
    domains: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not (_parse_topics(source.topics) & wanted):
            continue
        host = _source_search_domain(source)
        if host and host not in seen:
            seen.add(host)
            domains.append(host)
    return domains


def build_official_site_clause(domains: list[str], *, limit: int = 10) -> str:
    """Monta 'site:a OR site:b …' (limitado para não estourar a query DDG)."""
    picked = domains[:limit] if domains else list(_FALLBACK_SITES)
    if not picked:
        picked = list(_FALLBACK_SITES)
    return " OR ".join(f"site:{d}" for d in picked)


def official_search_query(
    db: Session,
    claim_text: str,
    base_query: str,
    themes: list[str] | None = None,
) -> str:
    """
    Query DDG priorizando oficiais dos temas selecionados pelo usuário.
    Sem tema selecionado → não força site: de oficiais (só a query base).
    """
    q = (base_query or "").strip()
    if themes is not None:
        topics = [t.strip().lower() for t in themes if t and str(t).strip()]
    else:
        topics = detect_topics(claim_text)
    if not topics:
        return q
    domains = official_domains_for_topics(db, topics)
    clause = build_official_site_clause(domains)
    if not q:
        return clause
    # Evita duplicar site: se o refine já colocou algo.
    if re.search(r"\bsite:", q, re.I):
        return q
    return f"{q} {clause}"
