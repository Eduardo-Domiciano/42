"""Comparação de claims econômicos com séries anuais do BCB (cache SGS)."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, ArticleBcbComparison
from app.schemas import BcbComparisonOut, ClaimAssessmentOut
from app.services.bcb_sgs import (
    ensure_economy_year,
    latest_point,
    parse_points,
)
from app.services.topic_officials import detect_topics

# Tolerância absoluta na diferença (pontos percentuais / R$).
_TOLERANCE = {
    "selic_meta": 0.15,
    "ipca_mensal": 0.15,
    "ipca_12m": 0.25,
    "usd_venda": 0.08,
}

_INDICATOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "selic_meta": ("selic", "taxa basica", "taxa básica", "copom"),
    "ipca_12m": (
        "ipca acumulado",
        "inflacao acumulada",
        "inflação acumulada",
        "12 meses",
        "doze meses",
    ),
    "ipca_mensal": ("ipca", "inflacao", "inflação"),
    "usd_venda": ("dolar", "dólar", "cambio", "câmbio", "usd"),
}

_NUM_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)(?!\d)",
)


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _parse_number(raw: str) -> float | None:
    s = raw.strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _numbers_in_text(text: str) -> list[float]:
    found: list[float] = []
    for m in _NUM_RE.finditer(text or ""):
        val = _parse_number(m.group(1))
        if val is None:
            continue
        # Ignora anos óbvios
        if 1990 <= val <= 2100 and val == int(val):
            continue
        found.append(val)
    return found


def _match_indicator(folded: str) -> str | None:
    # Ordem: mais específico primeiro (ipca_12m antes de ipca_mensal)
    for slug in ("selic_meta", "ipca_12m", "ipca_mensal", "usd_venda"):
        for kw in _INDICATOR_KEYWORDS[slug]:
            if _fold(kw) in folded:
                return slug
    return None


def article_has_economia(article: Article, claims: list[ClaimAssessmentOut]) -> bool:
    chunks = [
        article.title or "",
        article.excerpt or "",
        (article.body or "")[:4000],
    ]
    for c in claims:
        chunks.append(c.claim.canonical_text if c.claim else "")
    text = " ".join(chunks)
    return "economia" in detect_topics(text)


def resolve_comparison_year(article: Article) -> int:
    if article.published_at:
        return article.published_at.year
    return datetime.utcnow().year


def _compare_value(claimed: float, official: float, slug: str) -> str:
    tol = _TOLERANCE.get(slug, 0.2)
    diff = abs(claimed - official)
    if diff <= tol:
        return "match"
    if diff <= tol * 3:
        return "close"
    return "mismatch"


def run_bcb_comparison(
    db: Session,
    article: Article,
    claims: list[ClaimAssessmentOut],
    *,
    force: bool = False,
) -> list[BcbComparisonOut]:
    """
    Se a análise for de economia: garante séries do ano no cache e compara claims.
    Persiste resultado em article_bcb_comparisons.
    """
    if not article_has_economia(article, claims):
        return []

    year = resolve_comparison_year(article)

    if not force:
        cached = db.scalar(
            select(ArticleBcbComparison).where(
                ArticleBcbComparison.article_id == article.id,
                ArticleBcbComparison.year == year,
            )
        )
        if cached and cached.results_json not in (None, "", "[]"):
            try:
                raw = json.loads(cached.results_json)
                return [BcbComparisonOut.model_validate(x) for x in raw]
            except Exception:
                pass

    series_rows = ensure_economy_year(db, year, force=False)
    by_slug = {r.series_slug: r for r in series_rows}

    results: list[BcbComparisonOut] = []
    for assessment in claims:
        claim_text = assessment.claim.canonical_text if assessment.claim else ""
        folded = _fold(claim_text)
        slug = _match_indicator(folded)
        if not slug:
            continue
        nums = _numbers_in_text(claim_text)
        if not nums:
            continue
        claimed = nums[0]
        row = by_slug.get(slug)
        if not row:
            continue
        points = parse_points(row)
        point = latest_point(points)
        if not point:
            results.append(
                BcbComparisonOut(
                    claim_id=assessment.claim.id if assessment.claim else assessment.id,
                    claim_text=claim_text,
                    indicator_slug=slug,
                    indicator_name=row.series_name,
                    series_code=row.series_code,
                    year=year,
                    claimed_value=claimed,
                    official_value=None,
                    official_date=None,
                    status="no_official_data",
                    note=f"Série {row.series_code} sem pontos para {year} no cache/API.",
                    from_cache=True,
                )
            )
            continue
        official = float(point["valor"])
        status = _compare_value(claimed, official, slug)
        note = (
            f"Valor citado {claimed:g} vs BCB {official:g} "
            f"({point['data']}, série {row.series_code})."
        )
        results.append(
            BcbComparisonOut(
                claim_id=assessment.claim.id if assessment.claim else assessment.id,
                claim_text=claim_text,
                indicator_slug=slug,
                indicator_name=row.series_name,
                series_code=row.series_code,
                year=year,
                claimed_value=round(claimed, 4),
                official_value=round(official, 4),
                official_date=point["data"],
                status=status,
                note=note,
                from_cache=True,
            )
        )

    # Sem claim numérico: ainda registra que o ano foi carregado
    if not results:
        results.append(
            BcbComparisonOut(
                claim_id=0,
                claim_text="",
                indicator_slug="economia",
                indicator_name="Séries BCB do ano",
                series_code=0,
                year=year,
                claimed_value=None,
                official_value=None,
                official_date=None,
                status="year_cached",
                note=(
                    f"Tema economia: séries SGS de {year} em cache "
                    f"({len(series_rows)} série(s)). Nenhuma afirmativa "
                    "numérica de Selic/IPCA/dólar para comparar."
                ),
                from_cache=True,
            )
        )

    payload = json.dumps([r.model_dump() for r in results], ensure_ascii=False)
    now = datetime.utcnow()
    existing = db.scalar(
        select(ArticleBcbComparison).where(
            ArticleBcbComparison.article_id == article.id,
            ArticleBcbComparison.year == year,
        )
    )
    if existing:
        existing.results_json = payload
        existing.updated_at = now
    else:
        db.add(
            ArticleBcbComparison(
                article_id=article.id,
                year=year,
                results_json=payload,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()
    return results
