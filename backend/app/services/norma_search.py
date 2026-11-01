"""Busca FTS de normas (leis-main) e vínculo a claims com pistas legais."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, ClaimAssessment, ClaimNormaHit, Norma
from app.schemas import ClaimAssessmentOut
from app.services.themes_catalog import has_theme

# Pistas de conteúdo jurídico no texto / tema.
_LEGAL_RE = re.compile(
    r"(?i)\b("
    r"lei\s*n[º°o.]?\s*\d|"
    r"decreto(\s*[-–]?\s*lei)?\s*n[º°o.]?\s*\d|"
    r"medida\s+provis[oó]ria|"
    r"emenda\s+constitucional|"
    r"constitui[cç][aã]o|"
    r"cf\s*/?\s*88|"
    r"art\.?\s*\d|"
    r"urn:lex|"
    r"c[oó]digo\s+(civil|penal|tribut[aá]rio|de\s+processo)|"
    r"planalto\.gov|"
    r"normas\.leg\.br"
    r")\b"
)

_FTS_SPECIAL = re.compile(r'[^\wÀ-ÿ]+', re.UNICODE)


@dataclass
class NormaHit:
    norma: Norma
    score: float
    method: str
    snippet: str | None = None


def detect_legal_cues(
    *,
    texts: list[str],
    themes: list[str] | None = None,
    url: str | None = None,
) -> bool:
    """True se o artigo/claims pedem consulta a normas."""
    if has_theme(themes, "governo"):
        return True
    blob = " ".join(t for t in texts if t)
    if url and _LEGAL_RE.search(url):
        return True
    return bool(_LEGAL_RE.search(blob))


def sanitize_fts_query(query: str, *, max_terms: int = 12) -> str:
    """Monta MATCH FTS5 seguro (AND entre tokens)."""
    raw = (query or "").strip()
    if not raw:
        return ""
    # URN literal
    if raw.lower().startswith("urn:lex"):
        safe = re.sub(r'[^\w:.;\-/]', '', raw)
        return f'urn:"{safe}"' if safe else ""

    tokens = [t for t in _FTS_SPECIAL.split(raw) if len(t) >= 2]
    tokens = tokens[:max_terms]
    if not tokens:
        return ""
    # Aspas em cada token evita operadores FTS acidentais
    return " AND ".join(f'"{t}"' for t in tokens)


def search_normas(
    db: Session,
    query: str,
    *,
    vigente_only: bool = True,
    esfera: str | None = None,
    limit: int | None = None,
) -> list[NormaHit]:
    """SELECT via norma_fts MATCH + filtros em normas."""
    limit = limit if limit is not None else settings.norma_search_limit
    match = sanitize_fts_query(query)
    if not match:
        return []

    # rank do FTS5: quanto menor, melhor
    sql = """
        SELECT n.id, bm25(norma_fts) AS score
        FROM norma_fts
        JOIN normas n ON n.id = norma_fts.rowid
        WHERE norma_fts MATCH :q
    """
    params: dict[str, object] = {"q": match, "lim": limit}
    if vigente_only:
        sql += " AND n.revogada = 0"
    if esfera:
        sql += " AND n.esfera = :esfera"
        params["esfera"] = esfera
    sql += " ORDER BY score LIMIT :lim"

    try:
        rows = db.execute(text(sql), params).all()
    except Exception:
        # FTS ainda não migrado / query inválida
        return []

    if not rows:
        return []

    ids = [int(r[0]) for r in rows]
    score_by_id = {int(r[0]): float(r[1]) for r in rows}
    normas = {
        n.id: n
        for n in db.scalars(select(Norma).where(Norma.id.in_(ids))).all()
    }
    hits: list[NormaHit] = []
    for nid in ids:
        norma = normas.get(nid)
        if not norma:
            continue
        snippet = (norma.ementa or norma.titulo or "")[:280] or None
        hits.append(
            NormaHit(
                norma=norma,
                score=score_by_id.get(nid, 0.0),
                method="fts",
                snippet=snippet,
            )
        )
    return hits


def search_norma_by_urn(db: Session, urn: str) -> NormaHit | None:
    urn = (urn or "").strip()
    if not urn:
        return None
    norma = db.scalar(select(Norma).where(Norma.urn == urn))
    if not norma:
        return None
    return NormaHit(norma=norma, score=0.0, method="urn", snippet=norma.ementa)


def _claim_text(assessment: ClaimAssessmentOut) -> str:
    if assessment.claim:
        return assessment.claim.canonical_text or ""
    return ""


def _claim_id(assessment: ClaimAssessmentOut) -> int | None:
    if assessment.claim:
        return assessment.claim.id
    return None


def _merge_factors_json(existing: str | None, norma_hits: list[dict]) -> str:
    factors: list[str] = []
    try:
        raw = json.loads(existing or "[]")
    except json.JSONDecodeError:
        raw = []
    if isinstance(raw, dict):
        factors = list(raw.get("factors") or [])
        prev = list(raw.get("norma_hits") or [])
        # merge por urn
        by_urn = {h.get("urn"): h for h in prev if h.get("urn")}
        for h in norma_hits:
            by_urn[h["urn"]] = h
        norma_hits = list(by_urn.values())
    elif isinstance(raw, list):
        factors = [str(x) for x in raw]
    # fatores textuais curtos (compatível com UI)
    for h in norma_hits:
        label = f"norma:{h.get('urn')} — {h.get('titulo') or ''}"
        if h.get("revogada"):
            label += " (revogada)"
        if label not in factors:
            factors.append(label)
    return json.dumps(
        {"factors": factors, "norma_hits": norma_hits},
        ensure_ascii=False,
    )


def run_norma_lookup(
    db: Session,
    article: Article,
    claims: list[ClaimAssessmentOut],
    *,
    force: bool = False,
    themes: list[str] | None = None,
) -> list[dict]:
    """
    Se houver pistas legais, busca normas por claim e persiste claim_norma_hits.
    Retorna resumo [{claim_id, urn, titulo, revogada, score}].
    """
    if not settings.norma_search_enabled:
        return []

    texts = [
        article.title or "",
        article.excerpt or "",
        (article.body or "")[:4000],
        *(_claim_text(c) for c in claims),
    ]
    if not detect_legal_cues(texts=texts, themes=themes, url=article.url):
        return []

    summary: list[dict] = []
    for assessment in claims:
        cid = _claim_id(assessment)
        if cid is None:
            continue

        if not force:
            existing_rows = list(
                db.scalars(
                    select(ClaimNormaHit).where(ClaimNormaHit.claim_id == cid)
                ).all()
            )
            if existing_rows:
                for existing in existing_rows:
                    norma = db.get(Norma, existing.norma_id)
                    if norma:
                        summary.append(
                            {
                                "claim_id": cid,
                                "urn": norma.urn,
                                "titulo": norma.titulo,
                                "revogada": norma.revogada,
                                "score": existing.score,
                            }
                        )
                continue

        q = _claim_text(assessment)
        # URN explícita no claim
        urn_m = re.search(r"urn:lex:[^\s\"']+", q, re.I)
        hits: list[NormaHit] = []
        if urn_m:
            by_urn = search_norma_by_urn(db, urn_m.group(0))
            if by_urn:
                hits = [by_urn]
        if not hits:
            hits = search_normas(
                db, q, vigente_only=True, esfera="federal", limit=3
            )
        if not hits:
            # fallback: título do artigo
            hits = search_normas(
                db,
                article.title or q,
                vigente_only=True,
                esfera="federal",
                limit=2,
            )

        hit_payload: list[dict] = []
        for hit in hits:
            row = db.scalar(
                select(ClaimNormaHit).where(
                    ClaimNormaHit.claim_id == cid,
                    ClaimNormaHit.norma_id == hit.norma.id,
                )
            )
            if row:
                row.score = hit.score
                row.method = hit.method
                row.snippet = hit.snippet
            else:
                db.add(
                    ClaimNormaHit(
                        claim_id=cid,
                        norma_id=hit.norma.id,
                        score=hit.score,
                        method=hit.method,
                        snippet=hit.snippet,
                    )
                )
            payload = {
                "urn": hit.norma.urn,
                "titulo": hit.norma.titulo,
                "revogada": bool(hit.norma.revogada),
            }
            hit_payload.append(payload)
            summary.append(
                {
                    "claim_id": cid,
                    "urn": hit.norma.urn,
                    "titulo": hit.norma.titulo,
                    "revogada": bool(hit.norma.revogada),
                    "score": hit.score,
                }
            )

        if hit_payload:
            ca = db.scalar(
                select(ClaimAssessment).where(
                    ClaimAssessment.article_id == article.id,
                    ClaimAssessment.claim_id == cid,
                )
            )
            if ca:
                ca.factors_json = _merge_factors_json(ca.factors_json, hit_payload)

    db.commit()
    return summary
