from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import Article, Claim, ClaimAssessment, CrossReference, EvidenceItem
from app.schemas import (
    ClaimAssessmentOut,
    CrossReferenceOut,
    EvidenceItemOut,
    SourceOut,
)
from app.services.fetch_article import fetch_and_store_article, normalize_url
from app.services.heuristic_claims import claims_near_duplicate
from app.services.nn_embeddings import rank_articles_by_claim
from app.services.nn_runtime import get_embedder, nn_enabled
from app.services.stance import classify_stance
from app.services.web_search import search_news_urls

_STOP = {
    "sobre",
    "para",
    "como",
    "mais",
    "menos",
    "após",
    "antes",
    "ainda",
    "também",
    "pelo",
    "pela",
    "dos",
    "das",
    "uma",
    "uns",
    "este",
    "esta",
    "isso",
    "aquele",
    "segundo",
    "conforme",
}


def _query_from_claim(text: str) -> str:
    toks = [
        t
        for t in re.findall(r"\w{4,}", text.lower())
        if t not in _STOP and not t.isdigit()
    ]
    return " ".join(toks[:8]) or text[:80]


def _ownership_key(article: Article) -> str:
    if article.source:
        return (
            article.source.ownership_name
            or article.source.ownership_group
            or article.source.domain
            or f"source:{article.source_id}"
        )
    return f"url:{normalize_url(article.url)}"


def _authority_weight(article: Article) -> float:
    if not article.source:
        return 0.35
    tier = article.source.authority_tier or ""
    score = article.source.authority_score
    if score is not None:
        return float(score)
    if tier == "primary":
        return 0.95
    if tier == "secondary":
        return 0.65
    if tier == "low":
        return 0.35
    return 0.45


def _archive_peers(db: Session, claim_id: int, root: Article) -> list[Article]:
    """Artigos do acervo que já têm assessment (ou foram evidência) deste claim."""
    assessed_ids = list(
        db.scalars(
            select(ClaimAssessment.article_id)
            .where(
                ClaimAssessment.claim_id == claim_id,
                ClaimAssessment.article_id != root.id,
            )
            .limit(settings.crossref_max_peers * 2)
        ).all()
    )
    evidence_ids = list(
        db.scalars(
            select(EvidenceItem.evidence_article_id)
            .where(
                EvidenceItem.claim_id == claim_id,
                EvidenceItem.evidence_article_id != root.id,
            )
            .limit(settings.crossref_max_peers * 2)
        ).all()
    )
    ids = list(dict.fromkeys([*assessed_ids, *evidence_ids]))
    if not ids:
        return []
    return list(
        db.scalars(
            select(Article)
            .options(joinedload(Article.source))
            .where(Article.id.in_(ids))
        )
        .unique()
        .all()
    )


def _cached_stance(
    db: Session, claim_id: int, peer_id: int
) -> tuple[str, float, str, str] | None:
    """Reutiliza stance já gravada no acervo para o mesmo claim×peer."""
    row = db.scalar(
        select(EvidenceItem)
        .where(
            EvidenceItem.claim_id == claim_id,
            EvidenceItem.evidence_article_id == peer_id,
        )
        .order_by(EvidenceItem.created_at.desc())
    )
    if not row:
        return None
    note = row.note or "Stance reutilizada do acervo"
    if "acervo" not in note.lower():
        note = f"{note} | acervo"
    return row.stance, float(row.stance_confidence), note, "acervo"


def _local_peers(
    db: Session,
    claim_text: str,
    root: Article,
    *,
    pool: list[Article] | None = None,
) -> list[Article]:
    if pool is not None:
        return [a for a in pool if a.id != root.id]

    q = _query_from_claim(claim_text)
    terms = [t for t in q.split() if len(t) > 3][:4]
    if not terms:
        return []

    clauses = [Article.id != root.id]
    like_clauses = []
    for term in terms:
        like = f"%{term}%"
        like_clauses.append(
            or_(Article.title.ilike(like), Article.body.ilike(like))
        )
    pool_limit = settings.crossref_max_peers
    if nn_enabled() and settings.nn_embeddings_enabled:
        pool_limit = max(
            settings.crossref_max_peers,
            settings.crossref_max_peers * max(1, settings.nn_peer_pool_multiplier),
        )
    stmt = (
        select(Article)
        .options(joinedload(Article.source))
        .where(*clauses, or_(*like_clauses))
        .limit(pool_limit)
    )
    if root.published_at:
        start = root.published_at - timedelta(days=settings.crossref_window_days)
        end = root.published_at + timedelta(days=settings.crossref_window_days)
        stmt = stmt.where(
            or_(Article.published_at.is_(None), Article.published_at.between(start, end))
        )
    peers = list(db.scalars(stmt).unique().all())
    if peers and get_embedder():
        ranked = rank_articles_by_claim(
            claim_text, peers, top_k=settings.crossref_max_peers
        )
        return [a for a, _score in ranked]
    return peers[: settings.crossref_max_peers]


def _fetch_web_peers(db: Session, claim_text: str, root: Article) -> list[Article]:
    query = _query_from_claim(claim_text)
    # Prioriza oficiais na query também
    urls = search_news_urls(
        query, max_results=settings.crossref_max_peers, refine_query=True
    )
    official_urls = search_news_urls(
        f"{query} site:gov.br OR site:ibge.gov.br OR site:bcb.gov.br",
        max_results=max(2, settings.crossref_max_peers // 2),
        refine_query=False,
    )
    seen = {normalize_url(root.url)}
    peers: list[Article] = []
    for url in official_urls + urls:
        nurl = normalize_url(url)
        if nurl in seen:
            continue
        seen.add(nurl)
        try:
            art = fetch_and_store_article(db, url)
            art = db.scalar(
                select(Article)
                .options(joinedload(Article.source))
                .where(Article.id == art.id)
            )
            if art and art.id != root.id:
                peers.append(art)
        except Exception:
            continue
        if len(peers) >= settings.crossref_max_peers:
            break
    return peers


def _aggregate(
    root: Article,
    isolated_verdict: str,
    evidences: list[tuple[Article, str, float, str, str]],
) -> tuple[str, float, bool, int, list[str]]:
    """
    evidences: (article, stance, stance_conf, method, note)
    Retorna consensus, calibration, primary_veto, independent_voices, factors
    """
    factors: list[str] = []
    # Uma voz por ownership (pega a evidência de maior peso no grupo)
    by_owner: dict[str, tuple[Article, str, float]] = {}
    for art, stance, conf, _method, _note in evidences:
        if stance == "unrelated":
            continue
        owner = _ownership_key(art)
        weight = _authority_weight(art) * conf
        prev = by_owner.get(owner)
        if not prev or weight > prev[2]:
            by_owner[owner] = (art, stance, weight)

    root_owner = _ownership_key(root)
    same_owner = [o for o in by_owner if o == root_owner]
    if same_owner and len(by_owner) == 1:
        factors.append(
            f"Ownership (grupo dono): todas as evidências úteis são do mesmo grupo "
            f"({root_owner}) — eco, não consenso independente"
        )

    supports = 0.0
    refutes = 0.0
    related = 0.0
    primary_veto = False
    independent = 0

    for owner, (art, stance, weight) in by_owner.items():
        if owner == root_owner:
            factors.append(
                f"Evidência do mesmo Ownership (grupo dono) que a matéria original: {owner}"
            )
            # Conta com peso reduzido
            weight *= 0.35
        else:
            independent += 1

        tier = art.source.authority_tier if art.source else None
        if tier == "primary" and stance == "refutes":
            primary_veto = True
            factors.append(
                f"Veto de fonte primária: {art.source.name if art.source else art.url} refuta o claim"
            )
        if stance == "supports":
            supports += weight
        elif stance == "refutes":
            refutes += weight
        elif stance == "related":
            related += weight * 0.4

    if primary_veto:
        consensus = "disputed"
    elif supports > refutes * 1.2 and supports >= 0.5:
        consensus = "supported"
    elif refutes > supports * 1.2 and refutes >= 0.45:
        consensus = "disputed"
    elif supports + refutes + related < 0.3:
        consensus = "insufficient"
        factors.append("Poucas evidências independentes encontradas")
    else:
        consensus = "insufficient"
        factors.append("Sinais mistos ou só related — evidência insuficiente para consenso")

    factors.append(
        f"Vozes independentes (ownership distinto): {independent}; "
        f"peso supports={supports:.2f} refutes={refutes:.2f}"
    )

    # Calibração: F3 vs F4
    if isolated_verdict == consensus:
        calibration = 0.85
        factors.append("Calibração alta: veredito isolado (F3) alinhado ao cruzamento (F4)")
    elif isolated_verdict == "opinion":
        calibration = 0.5
        factors.append("Matéria/opinião — cruzamento factual limitado")
    elif {isolated_verdict, consensus} == {"supported", "disputed"}:
        calibration = 0.15
        factors.append("Calibração baixa: F3 e F4 discordam fortemente")
    else:
        calibration = 0.45
        factors.append("Calibração moderada: F3 e F4 parcialmente alinhados")

    return consensus, round(calibration, 3), primary_veto, independent, factors


def _unique_assessments(
    assessments: list[ClaimAssessmentOut],
) -> list[ClaimAssessmentOut]:
    """Uma entrada por claim_id e sem frases quase iguais."""
    by_id: dict[int, ClaimAssessmentOut] = {}
    for a in assessments:
        prev = by_id.get(a.claim.id)
        if prev is None or a.confidence > prev.confidence:
            by_id[a.claim.id] = a
    ordered = sorted(
        by_id.values(),
        key=lambda a: (a.confidence, a.score_internal_support),
        reverse=True,
    )
    unique: list[ClaimAssessmentOut] = []
    for a in ordered:
        if any(
            claims_near_duplicate(a.claim.canonical_text, u.claim.canonical_text)
            for u in unique
        ):
            continue
        unique.append(a)
    unique.sort(key=lambda a: a.id)
    return unique


def _dedupe_cross_outs(outs: list[CrossReferenceOut]) -> list[CrossReferenceOut]:
    by_claim: dict[int, CrossReferenceOut] = {}
    for x in outs:
        prev = by_claim.get(x.claim_id)
        if prev is None or x.calibration_score > prev.calibration_score:
            by_claim[x.claim_id] = x
    ordered = list(by_claim.values())
    unique: list[CrossReferenceOut] = []
    for x in ordered:
        if any(claims_near_duplicate(x.claim_text, u.claim_text) for u in unique):
            continue
        unique.append(x)
    return unique


def run_cross_reference_for_article(
    db: Session,
    root: Article,
    assessments: list[ClaimAssessmentOut],
    *,
    peer_pool: list[Article] | None = None,
    allow_llm_stance: bool = False,
    force: bool = False,
) -> list[CrossReferenceOut]:
    if not settings.crossref_enabled or not assessments:
        return []

    assessments = _unique_assessments(assessments)
    outs: list[CrossReferenceOut] = []

    for assessment in assessments[: settings.claim_max_per_article]:
        claim_id = assessment.claim.id
        existing = db.scalar(
            select(CrossReference).where(
                CrossReference.root_article_id == root.id,
                CrossReference.claim_id == claim_id,
            )
        )
        if existing and not force:
            outs.append(_cross_out(db, existing))
            continue
        if existing and force:
            for ev in list(
                db.scalars(
                    select(EvidenceItem).where(
                        EvidenceItem.root_article_id == root.id,
                        EvidenceItem.claim_id == claim_id,
                    )
                ).all()
            ):
                db.delete(ev)
            db.delete(existing)
            db.flush()

        claim = db.get(Claim, claim_id)
        if not claim:
            continue

        # Acervo primeiro: artigos já analisados para o mesmo claim
        archive = _archive_peers(db, claim_id, root)
        peers = list(archive)
        if peer_pool is not None:
            peers.extend(_local_peers(db, claim.canonical_text, root, pool=peer_pool))
        else:
            peers.extend(_local_peers(db, claim.canonical_text, root, pool=None))
            if len(peers) < settings.crossref_min_local_before_web:
                peers.extend(_fetch_web_peers(db, claim.canonical_text, root))

        uniq: dict[int, Article] = {}
        for p in peers:
            if p.id != root.id and p.id not in uniq:
                uniq[p.id] = p
        # Mantém ordem: acervo → local → web
        peers = list(uniq.values())[: settings.crossref_max_peers]

        evidence_rows: list[EvidenceItem] = []
        agg_input: list[tuple[Article, str, float, str, str]] = []
        archive_hits = 0

        for peer in peers:
            cached = _cached_stance(db, claim_id, peer.id)
            if cached:
                stance, conf, note, method = cached
                archive_hits += 1
            else:
                stance, conf, note, method = classify_stance(
                    claim.canonical_text,
                    peer,
                    allow_llm=allow_llm_stance and settings.crossref_use_llm_stance,
                )
            weight = _authority_weight(peer) * conf
            same_owner = _ownership_key(peer) == _ownership_key(root)
            row = EvidenceItem(
                claim_id=claim_id,
                root_article_id=root.id,
                evidence_article_id=peer.id,
                stance=stance,
                weight=weight,
                stance_confidence=conf,
                method=method,
                same_ownership=same_owner,
                note=note,
                created_at=datetime.utcnow(),
            )
            db.add(row)
            evidence_rows.append(row)
            agg_input.append((peer, stance, conf, method, note))

        consensus, calibration, veto, voices, factors = _aggregate(
            root, assessment.verdict, agg_input
        )
        if archive:
            factors.insert(
                0,
                f"Acervo: {len(archive)} artigo(s) já ligados a este claim; "
                f"{archive_hits} stance(s) reutilizada(s)",
            )
        xref = CrossReference(
            root_article_id=root.id,
            claim_id=claim_id,
            isolated_verdict=assessment.verdict,
            consensus_verdict=consensus,
            calibration_score=calibration,
            primary_veto=veto,
            independent_voices=voices,
            factors_json=json.dumps(factors, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
        db.add(xref)
        db.flush()
        for row in evidence_rows:
            db.refresh(row)
        db.refresh(xref)
        outs.append(_cross_out(db, xref))

    db.commit()
    return _dedupe_cross_outs(outs)


def _cross_out(db: Session, xref: CrossReference) -> CrossReferenceOut:
    evidences = list(
        db.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.root_article_id == xref.root_article_id,
                EvidenceItem.claim_id == xref.claim_id,
            )
            .order_by(EvidenceItem.weight.desc())
        ).all()
    )
    claim = db.get(Claim, xref.claim_id)
    factors: list[str] = []
    try:
        factors = json.loads(xref.factors_json or "[]")
    except json.JSONDecodeError:
        pass

    evidence_outs: list[EvidenceItemOut] = []
    for ev in evidences:
        art = db.scalar(
            select(Article)
            .options(joinedload(Article.source))
            .where(Article.id == ev.evidence_article_id)
        )
        if not art:
            continue
        source_out = SourceOut.model_validate(art.source) if art.source else None
        evidence_outs.append(
            EvidenceItemOut(
                id=ev.id,
                stance=ev.stance,
                weight=ev.weight,
                stance_confidence=ev.stance_confidence,
                method=ev.method,
                same_ownership=ev.same_ownership,
                note=ev.note,
                article_id=art.id,
                article_title=art.title,
                article_url=art.url,
                source=source_out,
                ownership_name=_ownership_key(art)
                if art.source
                else None,
            )
        )

    return CrossReferenceOut(
        claim_id=xref.claim_id,
        claim_text=claim.canonical_text if claim else "",
        isolated_verdict=xref.isolated_verdict,
        consensus_verdict=xref.consensus_verdict,
        calibration_score=xref.calibration_score,
        primary_veto=xref.primary_veto,
        independent_voices=xref.independent_voices,
        factors=factors,
        evidences=evidence_outs,
    )
