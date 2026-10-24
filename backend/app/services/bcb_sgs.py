"""Cliente SGS do Banco Central + cache anual em SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BcbSeriesAnnual

logger = logging.getLogger(__name__)

SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"

# Séries oficiais usadas na comparação econômica (código SGS).
BCB_SERIES: dict[str, dict] = {
    "selic_meta": {
        # SGS 4189 — Taxa Selic (% a.a.); 4326 costuma 404 na API pública
        "code": 4189,
        "name": "Taxa Selic (% a.a.)",
    },
    "ipca_mensal": {
        "code": 433,
        "name": "IPCA variação mensal (%)",
    },
    "ipca_12m": {
        "code": 13522,
        "name": "IPCA acumulado 12 meses (%)",
    },
    "usd_venda": {
        "code": 1,
        "name": "Dólar americano venda (R$)",
    },
}


def _year_bounds(year: int) -> tuple[str, str]:
    return f"01/01/{year}", f"31/12/{year}"


def fetch_series_year(series_code: int, year: int, *, timeout: float = 25.0) -> list[dict]:
    """Baixa pontos da série no ano civil (sempre anual)."""
    data_ini, data_fim = _year_bounds(year)
    url = SGS_BASE.format(code=series_code)
    params = {
        "formato": "json",
        "dataInicial": data_ini,
        "dataFinal": data_fim,
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        data_s = str(row.get("data") or "").strip()
        valor_s = str(row.get("valor") or "").strip().replace(",", ".")
        if not data_s or not valor_s:
            continue
        try:
            float(valor_s)
        except ValueError:
            continue
        out.append({"data": data_s, "valor": valor_s})
    return out


def get_cached_series(
    db: Session, series_code: int, year: int
) -> BcbSeriesAnnual | None:
    return db.scalar(
        select(BcbSeriesAnnual).where(
            BcbSeriesAnnual.series_code == series_code,
            BcbSeriesAnnual.year == year,
        )
    )


def ensure_series_year(
    db: Session,
    *,
    slug: str,
    series_code: int,
    series_name: str,
    year: int,
    force: bool = False,
) -> BcbSeriesAnnual:
    """Garante série+ano no banco; busca na API só se faltar (ou force)."""
    existing = get_cached_series(db, series_code, year)
    if existing and not force and existing.points_json not in (None, "", "[]"):
        return existing

    try:
        points = fetch_series_year(series_code, year)
    except Exception as exc:
        logger.warning("Falha SGS %s/%s: %s", series_code, year, exc)
        points = []

    # Não apaga cache bom se a API falhou ou voltou vazia.
    if not points and existing and existing.points_json not in (None, "", "[]"):
        return existing

    payload = json.dumps(points, ensure_ascii=False)
    now = datetime.utcnow()
    if existing:
        if points or force:
            existing.series_slug = slug
            existing.series_name = series_name
            existing.points_json = payload
            existing.fetched_at = now
            db.commit()
            db.refresh(existing)
        return existing

    row = BcbSeriesAnnual(
        series_code=series_code,
        series_slug=slug,
        series_name=series_name,
        year=year,
        points_json=payload,
        fetched_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ensure_economy_year(db: Session, year: int, *, force: bool = False) -> list[BcbSeriesAnnual]:
    """Garante todas as séries econômicas do ano no cache."""
    rows: list[BcbSeriesAnnual] = []
    for slug, meta in BCB_SERIES.items():
        rows.append(
            ensure_series_year(
                db,
                slug=slug,
                series_code=int(meta["code"]),
                series_name=str(meta["name"]),
                year=year,
                force=force,
            )
        )
    return rows


def parse_points(row: BcbSeriesAnnual) -> list[dict]:
    try:
        data = json.loads(row.points_json or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def latest_point(points: list[dict]) -> dict | None:
    if not points:
        return None
    return points[-1]
