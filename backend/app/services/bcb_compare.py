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
from app.services.themes_catalog import has_theme

# Tolerância absoluta na diferença (pontos percentuais / R$).
_TOLERANCE = {
    "selic_meta": 0.25,
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
        if 1990 <= val <= 2100 and val == int(val):
            continue
        found.append(val)
    return found


def _match_indicators(folded: str) -> list[str]:
    """Todos os indicadores citados (ordem: mais específico primeiro)."""
    found: list[str] = []
    for slug in ("selic_meta", "ipca_12m", "ipca_mensal", "usd_venda"):
        for kw in _INDICATOR_KEYWORDS[slug]:
            if _fold(kw) in folded:
                # Evita ipca_mensal se já pegou ipca_12m
                if slug == "ipca_mensal" and "ipca_12m" in found:
                    break
                found.append(slug)
                break
    return found


def _number_near_keywords(
    text: str,
    keywords: tuple[str, ...],
    *,
    allow_fallback: bool = False,
) -> float | None:
    """Busca número perto do termo no texto já sem acento (índices alinhados)."""
    folded = _fold(text)
    for kw in keywords:
        needle = _fold(kw)
        idx = folded.find(needle)
        if idx < 0:
            continue
        # Preferir número depois do termo (ex.: "IPCA ... 4,3%")
        after = folded[idx : idx + len(needle) + 56]
        nums_after = _numbers_in_text(after)
        if nums_after:
            return nums_after[0]
        before = folded[max(0, idx - 24) : idx + len(needle)]
        nums_before = _numbers_in_text(before)
        if nums_before:
            return nums_before[-1]
    if allow_fallback:
        nums = _numbers_in_text(text)
        return nums[0] if nums else None
    return None


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


def _cache_incomplete(results: list[BcbComparisonOut]) -> bool:
    return any(r.status == "no_official_data" for r in results)


def run_bcb_comparison(
    db: Session,
    article: Article,
    claims: list[ClaimAssessmentOut],
    *,
    force: bool = False,
    themes: list[str] | None = None,
) -> list[BcbComparisonOut]:
    """
    Só roda se o usuário marcou o tema \"economia\".
    Garante séries do ano no cache e compara claims; persiste em article_bcb_comparisons.
    """
    if not has_theme(themes, "economia"):
        return []

    year = resolve_comparison_year(article)

    # Séries anuais ficam em cache; a comparação artigo×BCB é recalculada
    # (barata) para não servir resultado antigo com mapeamento errado.
    series_rows = ensure_economy_year(db, year, force=False)
    if any(parse_points(r) == [] for r in series_rows):
        series_rows = ensure_economy_year(db, year, force=True)

    by_slug = {r.series_slug: r for r in series_rows}
    results: list[BcbComparisonOut] = []
    seen: set[tuple[int, str]] = set()

    for assessment in claims:
        claim_text = assessment.claim.canonical_text if assessment.claim else ""
        folded = _fold(claim_text)
        claim_id = assessment.claim.id if assessment.claim else assessment.id
        slugs = _match_indicators(folded)
        for slug in slugs:
            key = (claim_id, slug)
            if key in seen:
                continue
            seen.add(key)
            claimed = _number_near_keywords(
                claim_text,
                _INDICATOR_KEYWORDS[slug],
                allow_fallback=len(slugs) == 1,
            )
            row = by_slug.get(slug)
            if not row:
                continue
            if claimed is None:
                continue
            points = parse_points(row)
            point = latest_point(points)
            if not point:
                results.append(
                    BcbComparisonOut(
                        claim_id=claim_id,
                        claim_text=claim_text,
                        indicator_slug=slug,
                        indicator_name=row.series_name,
                        series_code=row.series_code,
                        year=year,
                        claimed_value=round(claimed, 4),
                        official_value=None,
                        official_date=None,
                        status="no_official_data",
                        note=(
                            f"Série {row.series_code} sem pontos para {year} "
                            f"no cache/API."
                        ),
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
                    claim_id=claim_id,
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

    # Sempre inclui painel das séries oficiais do ano (contexto)
    for row in series_rows:
        point = latest_point(parse_points(row))
        if point:
            results.append(
                BcbComparisonOut(
                    claim_id=0,
                    claim_text="",
                    indicator_slug=row.series_slug,
                    indicator_name=f"[BCB] {row.series_name}",
                    series_code=row.series_code,
                    year=year,
                    claimed_value=None,
                    official_value=round(float(point["valor"]), 4),
                    official_date=point["data"],
                    status="official_series",
                    note=(
                        f"Dado oficial em cache para {year} "
                        f"(série SGS {row.series_code})."
                    ),
                    from_cache=True,
                )
            )
        else:
            results.append(
                BcbComparisonOut(
                    claim_id=0,
                    claim_text="",
                    indicator_slug=row.series_slug,
                    indicator_name=f"[BCB] {row.series_name}",
                    series_code=row.series_code,
                    year=year,
                    claimed_value=None,
                    official_value=None,
                    official_date=None,
                    status="no_official_data",
                    note=f"Não foi possível obter a série {row.series_code} de {year}.",
                    from_cache=True,
                )
            )

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
                    f"Tema economia detectado para {year}, mas sem séries "
                    f"nem números comparáveis neste texto."
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
