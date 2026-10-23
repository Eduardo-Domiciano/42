from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, ArticleClaim, Claim, ClaimAssessment
from app.schemas import ClaimAssessmentOut, ClaimOut
from app.services.content_classifier import classify_content
from app.services.heuristic_claims import (
    ClaimScores,
    RawClaim,
    claims_near_duplicate,
    extract_claims_heuristic,
    fingerprint,
    score_claim_heuristic,
)
from app.services.llm_client import chat_json, llm_configured


_SYSTEM = """Você analisa notícias brasileiras para fact-checking.
Responda APENAS JSON válido com esta forma:
{
  "claims": [
    {
      "text": "afirmação canônica checável",
      "checkability": "checkable|opinion|unclear",
      "entities": ["..."],
      "time_scope": "texto ou null",
      "place_scope": "texto ou null",
      "scores": {
        "temporal": 0.0,
        "geographic": 0.0,
        "partisan": 0.0,
        "distortion": 0.0,
        "internal_support": 0.0
      },
      "verdict": "supported|disputed|insufficient|opinion",
      "confidence": 0.0,
      "justification": "breve",
      "factors": ["..."],
      "excerpts": ["trechos curtos do texto"]
    }
  ]
}
Regras:
- Extraia no máximo 5 claims checáveis; ignore opinião pura.
- Scores de 0 a 1. partisan e distortion altos = mais framing/risco.
- NÃO declare verdadeiro/falso absoluto sem evidência externa; prefira insufficient.
- supported só se o próprio texto tiver suporte interno forte (números, citações, atos).
"""


def _scores_from_llm(raw: dict) -> ClaimScores | None:
    scores = raw.get("scores") or {}
    try:
        return ClaimScores(
            temporal=float(scores.get("temporal", 0.5)),
            geographic=float(scores.get("geographic", 0.5)),
            partisan=float(scores.get("partisan", 0.5)),
            distortion=float(scores.get("distortion", 0.5)),
            internal_support=float(scores.get("internal_support", 0.5)),
            verdict=str(raw.get("verdict") or "insufficient"),
            confidence=float(raw.get("confidence") or 0.4),
            justification=str(raw.get("justification") or "Avaliação LLM"),
            factors=[str(f) for f in (raw.get("factors") or [])][:12],
            excerpts=[str(e) for e in (raw.get("excerpts") or [])][:4],
        )
    except (TypeError, ValueError):
        return None


def _llm_claims(article: Article) -> list[tuple[RawClaim, ClaimScores]] | None:
    if not llm_configured() or not settings.claim_use_llm:
        return None

    title = article.title or ""
    # Corpo curto no modelo local — menos tokens / menos pressão de RAM
    body_limit = 2500 if settings.llm_provider != "openrouter" else 6000
    body = (article.body or "")[:body_limit]
    published = article.published_at.isoformat() if article.published_at else None
    source_name = article.source.name if article.source else None
    user = (
        f"Título: {title}\n"
        f"Fonte: {source_name}\n"
        f"Publicado em: {published}\n"
        f"URL: {article.url}\n\n"
        f"Corpo:\n{body}"
    )
    data = chat_json(
        _SYSTEM,
        user,
        model=settings.local_llm_model if settings.llm_provider != "openrouter" else None,
        timeout=settings.llm_timeout_seconds,
    )
    if not data or "claims" not in data:
        return None

    out: list[tuple[RawClaim, ClaimScores]] = []
    for item in data.get("claims") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if len(text) < 20:
            continue
        checkability = str(item.get("checkability") or "unclear")
        if checkability == "opinion":
            continue
        scores = _scores_from_llm(item)
        if not scores:
            continue
        raw = RawClaim(
            text=text[:500],
            checkability=checkability,
            entities=[str(e) for e in (item.get("entities") or [])][:8],
            time_scope=item.get("time_scope"),
            place_scope=item.get("place_scope"),
        )
        out.append((raw, scores))
    return out or None


def _heuristic_pairs(article: Article) -> list[tuple[RawClaim, ClaimScores]]:
    pairs: list[tuple[RawClaim, ClaimScores]] = []
    for raw in extract_claims_heuristic(article):
        pairs.append((raw, score_claim_heuristic(article, raw)))
    return pairs


def _dedupe_pairs(
    pairs: list[tuple[RawClaim, ClaimScores]],
) -> list[tuple[RawClaim, ClaimScores]]:
    """Remove fingerprint igual e frases quase iguais (mantém maior suporte/confiança)."""
    kept: list[tuple[RawClaim, ClaimScores]] = []
    seen_fp: set[str] = set()
    for raw, scores in pairs:
        fp = fingerprint(raw.text)
        if fp in seen_fp:
            continue
        dup_idx = next(
            (
                i
                for i, (prev, _) in enumerate(kept)
                if claims_near_duplicate(raw.text, prev.text)
            ),
            None,
        )
        if dup_idx is not None:
            prev_raw, prev_scores = kept[dup_idx]
            # Prefere texto mais longo / maior suporte interno
            better = (
                scores.internal_support,
                scores.confidence,
                len(raw.text),
            ) > (
                prev_scores.internal_support,
                prev_scores.confidence,
                len(prev_raw.text),
            )
            if better:
                seen_fp.discard(fingerprint(prev_raw.text))
                kept[dup_idx] = (raw, scores)
                seen_fp.add(fp)
            continue
        seen_fp.add(fp)
        kept.append((raw, scores))
    return kept


def _collapse_duplicate_assessments(
    db: Session, rows: list[ClaimAssessment]
) -> list[ClaimAssessment]:
    """Remove assessments duplicados do mesmo artigo (mesmo claim ou near-dup)."""
    # Carrega claims para comparar texto
    for row in rows:
        if row.claim is None:
            db.refresh(row, attribute_names=["claim"])

    by_claim: dict[int, ClaimAssessment] = {}
    for row in sorted(rows, key=lambda r: r.id):
        prev = by_claim.get(row.claim_id)
        if prev is None:
            by_claim[row.claim_id] = row
            continue
        keep_new = (row.confidence, row.score_internal_support) > (
            prev.confidence,
            prev.score_internal_support,
        )
        if keep_new:
            db.delete(prev)
            by_claim[row.claim_id] = row
        else:
            db.delete(row)

    survivors = list(by_claim.values())
    survivors.sort(
        key=lambda r: (r.confidence, r.score_internal_support, r.id), reverse=True
    )
    final: list[ClaimAssessment] = []
    for row in survivors:
        text = row.claim.canonical_text if row.claim else ""
        if any(
            claims_near_duplicate(text, s.claim.canonical_text if s.claim else "")
            for s in final
        ):
            db.delete(row)
            continue
        final.append(row)
    final.sort(key=lambda r: r.id)
    return final


def _get_or_create_claim(db: Session, raw: RawClaim) -> Claim:
    fp = fingerprint(raw.text)
    existing = db.scalar(select(Claim).where(Claim.fingerprint == fp))
    if existing:
        return existing
    # Near-dup em claims já no banco (grafia antiga / pontuação)
    candidates = db.scalars(select(Claim).order_by(Claim.id.desc()).limit(80)).all()
    for cand in candidates:
        if claims_near_duplicate(raw.text, cand.canonical_text):
            return cand
    claim = Claim(
        canonical_text=raw.text,
        fingerprint=fp,
        checkability=raw.checkability,
        entities_json=json.dumps(raw.entities, ensure_ascii=False),
        time_scope=raw.time_scope,
        place_scope=raw.place_scope,
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    db.add(claim)
    db.flush()
    return claim


def ensure_claim_assessments(
    db: Session,
    article: Article,
    *,
    force: bool = False,
    allow_llm: bool = True,
) -> list[ClaimAssessmentOut]:
    """Extrai/avalia claims do artigo e persiste. Idempotente salvo force=True."""
    if article.content_type in {"opinion", "editorial"}:
        classification = classify_content(article)
        if classification.content_type in {"opinion", "editorial"} and not force:
            # Ainda assim tenta extrair se houver fatos embutidos
            pass

    existing = list(
        db.scalars(
            select(ClaimAssessment).where(ClaimAssessment.article_id == article.id)
        ).all()
    )
    if existing and not force:
        cleaned = _collapse_duplicate_assessments(db, existing)
        db.commit()
        for row in cleaned:
            db.refresh(row)
            if row.claim:
                db.refresh(row.claim)
        return [_assessment_out(a) for a in cleaned]

    if existing and force:
        for row in existing:
            db.delete(row)
        db.flush()

    pairs = None
    method = "heuristic"
    if allow_llm:
        pairs = _llm_claims(article)
        if pairs:
            method = "llm"

    if not pairs:
        pairs = _heuristic_pairs(article)
        method = "heuristic"

    pairs = _dedupe_pairs(pairs)

    results: list[ClaimAssessment] = []
    seen_claim_ids: set[int] = set()
    for raw, scores in pairs[: settings.claim_max_per_article]:
        claim = _get_or_create_claim(db, raw)
        if claim.id in seen_claim_ids:
            continue
        # Já existe assessment deste claim neste artigo?
        prior = db.scalar(
            select(ClaimAssessment).where(
                ClaimAssessment.article_id == article.id,
                ClaimAssessment.claim_id == claim.id,
            )
        )
        if prior and not force:
            seen_claim_ids.add(claim.id)
            results.append(prior)
            continue

        claim.last_seen_at = datetime.utcnow()
        seen_claim_ids.add(claim.id)

        link = db.scalar(
            select(ArticleClaim).where(
                ArticleClaim.article_id == article.id,
                ArticleClaim.claim_id == claim.id,
            )
        )
        if not link:
            db.add(ArticleClaim(article_id=article.id, claim_id=claim.id))

        assessment = ClaimAssessment(
            claim_id=claim.id,
            article_id=article.id,
            method=method,
            score_temporal=scores.temporal,
            score_geographic=scores.geographic,
            score_partisan=scores.partisan,
            score_distortion=scores.distortion,
            score_internal_support=scores.internal_support,
            verdict=scores.verdict,
            confidence=scores.confidence,
            justification=scores.justification,
            factors_json=json.dumps(scores.factors, ensure_ascii=False),
            excerpts_json=json.dumps(scores.excerpts, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
        db.add(assessment)
        results.append(assessment)

    db.flush()
    results = _collapse_duplicate_assessments(db, results)
    db.commit()
    for row in results:
        db.refresh(row)
        db.refresh(row.claim)

    return [_assessment_out(a) for a in results]


def _assessment_out(row: ClaimAssessment) -> ClaimAssessmentOut:
    claim = row.claim
    entities: list[str] = []
    if claim and claim.entities_json:
        try:
            entities = json.loads(claim.entities_json)
        except json.JSONDecodeError:
            entities = []
    factors: list[str] = []
    excerpts: list[str] = []
    try:
        factors = json.loads(row.factors_json or "[]")
        excerpts = json.loads(row.excerpts_json or "[]")
    except json.JSONDecodeError:
        pass

    return ClaimAssessmentOut(
        id=row.id,
        method=row.method,
        verdict=row.verdict,
        confidence=row.confidence,
        justification=row.justification,
        score_temporal=row.score_temporal,
        score_geographic=row.score_geographic,
        score_partisan=row.score_partisan,
        score_distortion=row.score_distortion,
        score_internal_support=row.score_internal_support,
        factors=factors,
        excerpts=excerpts,
        claim=ClaimOut(
            id=claim.id,
            canonical_text=claim.canonical_text,
            checkability=claim.checkability,
            entities=entities,
            time_scope=claim.time_scope,
            place_scope=claim.place_scope,
        ),
    )


def aggregate_claim_verdict(assessments: list[ClaimAssessmentOut]) -> str | None:
    if not assessments:
        return None
    verdicts = [a.verdict for a in assessments]
    if all(v == "opinion" for v in verdicts):
        return "opinion"
    if any(v == "disputed" for v in verdicts):
        return "disputed"
    if any(v == "supported" for v in verdicts) and not any(
        v == "disputed" for v in verdicts
    ):
        return "insufficient"  # supported interno ainda precisa F4
    return "insufficient"
