from __future__ import annotations

from datetime import datetime

from app.models import Article
from app.schemas import (
    ArticleAnalysisOut,
    ClaimAssessmentOut,
    CrossReferenceOut,
    TopicPanoramaOut,
)
from app.services.bias_catalog import bias_label_pt
from app.services.claim_pipeline import aggregate_claim_verdict
from app.services.content_classifier import classify_content


def analyze_article(
    article: Article,
    *,
    claims: list[ClaimAssessmentOut] | None = None,
) -> ArticleAnalysisOut:
    source = article.source
    tier = source.authority_tier if source else None
    classification = classify_content(article)
    factors: list[str] = list(classification.reasons)
    method = "heuristic"

    if source:
        factors.append(f"Fonte catalogada: {source.name} ({tier or 'sem tier'})")
        ownership = source.ownership_name or source.ownership_group
        if ownership:
            factors.append(f"Ownership: {ownership}")
        if source.bias_label:
            score = (
                f", score {source.bias_score:+.2f}"
                if source.bias_score is not None
                else ""
            )
            factors.append(
                f"Bias catálogo v{source.bias_catalog_version or '?'}: "
                f"{bias_label_pt(source.bias_label)}{score}"
            )
        if source.bias_note:
            factors.append(source.bias_note)
    else:
        factors.append("Fonte fora do catálogo BR — autoridade e bias desconhecidos")

    body = article.body or ""
    if len(body) < 200:
        factors.append("Corpo curto; risco de contexto incompleto")
    else:
        factors.append(f"Corpo com ~{len(body)} caracteres")

    temporal = "desconhecido"
    if article.published_at:
        published = article.published_at.replace(tzinfo=None)
        age_days = (datetime.utcnow() - published).days
        if age_days < 0:
            temporal = "data futura — verificar"
            factors.append("Data de publicação no futuro")
        elif age_days > 365:
            temporal = "conteúdo antigo — checar se está sendo usado como atual"
            factors.append(f"Publicado há ~{age_days} dias")
        else:
            temporal = "data de publicação presente e plausível"
            factors.append(f"Publicado há ~{age_days} dias")
    else:
        factors.append("Sem data de publicação detectada")

    if classification.content_type in {"opinion", "editorial"}:
        verdict = "opinion"
        partiality = (
            "Conteúdo classificado como opinião/editorial — não tratar como fato checável"
        )
        factors.append("Veredito preliminar: opinião")
    elif tier == "primary" or classification.content_type == "official_document":
        partiality = (
            "Fonte/documento oficial — parcialidade institucional possível, "
            "alta autoridade para o ato ou dado publicado"
        )
        verdict = "insufficient"
        factors.append("Análise isolada: aguarda cruzamento com outras fontes (F4)")
    elif source and source.bias_label in {"left", "right"}:
        partiality = (
            f"Veículo com linha editorial {bias_label_pt(source.bias_label)} "
            "no catálogo — framing partidário mais provável"
        )
        verdict = "insufficient"
    elif source and source.bias_label in {"center_left", "center_right"}:
        partiality = (
            f"Veículo {bias_label_pt(source.bias_label)} no catálogo — "
            "pode haver framing editorial moderado"
        )
        verdict = "insufficient"
    elif source:
        partiality = "Veículo catalogado com bias próximo ao centro ou institucional"
        verdict = "insufficient"
    else:
        partiality = "Parcialidade não classificada"
        verdict = "insufficient"

    if claims:
        methods = {c.method for c in claims}
        if "llm" in methods:
            method = "llm+source"
        else:
            method = "heuristic+claims"
        claim_verdict = aggregate_claim_verdict(claims)
        if claim_verdict:
            verdict = claim_verdict
            factors.append(
                f"F3: {len(claims)} claim(s); veredito agregado={claim_verdict}"
            )
        avg_support = sum(c.score_internal_support for c in claims) / len(claims)
        avg_dist = sum(c.score_distortion for c in claims) / len(claims)
        factors.append(
            f"Média suporte interno={avg_support:.2f}; distorção={avg_dist:.2f}"
        )

    return ArticleAnalysisOut(
        content_type_guess=classification.content_type,
        content_type_confidence=classification.confidence,
        authority_tier=tier,
        bias_label=source.bias_label if source else None,
        bias_score=source.bias_score if source else None,
        bias_catalog_version=source.bias_catalog_version if source else None,
        ownership_name=(source.ownership_name if source else None),
        source_partiality_note=partiality,
        temporal_coherence=temporal,
        preliminary_verdict=verdict,
        analysis_method=method,
        factors=factors,
    )


def build_panorama(
    articles: list[Article],
    *,
    article_claims: dict[int, list[ClaimAssessmentOut]] | None = None,
    article_xrefs: dict[int, list[CrossReferenceOut]] | None = None,
    discarded_relevance: int = 0,
    discarded_date: int = 0,
    candidates_considered: int = 0,
) -> TopicPanoramaOut:
    tiers: dict[str, int] = {}
    bias_labels: dict[str, int] = {}
    content_types: dict[str, int] = {}
    claim_verdicts: dict[str, int] = {}
    consensus_verdicts: dict[str, int] = {}
    ownerships: set[str] = set()
    source_ids: set[int] = set()
    total_claims = 0
    total_cross_refs = 0
    calibration_sum = 0.0
    article_claims = article_claims or {}
    article_xrefs = article_xrefs or {}

    for article in articles:
        if article.source_id:
            source_ids.add(article.source_id)
        tier = (article.source.authority_tier if article.source else None) or "unknown"
        tiers[tier] = tiers.get(tier, 0) + 1

        label = (article.source.bias_label if article.source else None) or "unknown"
        bias_labels[label] = bias_labels.get(label, 0) + 1

        ctype = classify_content(article).content_type
        content_types[ctype] = content_types.get(ctype, 0) + 1

        if article.source:
            own = article.source.ownership_name or article.source.ownership_group
            if own:
                ownerships.add(own)

        for assessment in article_claims.get(article.id, []):
            total_claims += 1
            claim_verdicts[assessment.verdict] = (
                claim_verdicts.get(assessment.verdict, 0) + 1
            )

        for xref in article_xrefs.get(article.id, []):
            total_cross_refs += 1
            consensus_verdicts[xref.consensus_verdict] = (
                consensus_verdicts.get(xref.consensus_verdict, 0) + 1
            )
            calibration_sum += xref.calibration_score

    notes = [
        "F4: panorama com bias/ownership, claims e cruzamento (stance + calibração).",
    ]
    if candidates_considered or discarded_relevance or discarded_date:
        notes.append(
            f"Filtro de tema: {len(articles)} aceito(s) de {candidates_considered} "
            f"candidato(s); {discarded_relevance} descartado(s) por baixa relevância"
            + (
                f"; {discarded_date} fora do período/sem data"
                if discarded_date
                else ""
            )
            + "."
        )
    if tiers.get("primary", 0) == 0:
        notes.append("Nenhuma fonte primária/oficial no conjunto — veredito conservador.")
    if len(source_ids) <= 1 and articles:
        notes.append("Pouca diversidade de veículos; risco de eco da mesma narrativa.")
    if len(ownerships) == 1 and len(articles) > 1:
        notes.append(
            f"Todos os artigos catalogados apontam para o mesmo Ownership (grupo dono): "
            f"{next(iter(ownerships))}."
        )
    partisan = bias_labels.get("left", 0) + bias_labels.get("right", 0)
    if partisan and partisan == len(articles):
        notes.append("Conjunto só com veículos de linha left/right explícita no catálogo.")
    if total_claims:
        notes.append(f"{total_claims} Claims (afirmativas) avaliados no conjunto.")
    else:
        notes.append("Nenhum Claim (afirmativa) checável extraído neste lote.")
    if total_cross_refs:
        notes.append(
            f"{total_cross_refs} cruzamento(s); calibração média "
            f"{calibration_sum / total_cross_refs:.2f}."
        )

    return TopicPanoramaOut(
        total_articles=len(articles),
        distinct_sources=len(source_ids),
        distinct_ownerships=len(ownerships),
        authority_tiers=tiers,
        bias_labels=bias_labels,
        content_types=content_types,
        claim_verdicts=claim_verdicts,
        consensus_verdicts=consensus_verdicts,
        total_claims=total_claims,
        total_cross_refs=total_cross_refs,
        avg_calibration=(
            round(calibration_sum / total_cross_refs, 3) if total_cross_refs else None
        ),
        candidates_considered=candidates_considered,
        discarded_relevance=discarded_relevance,
        discarded_date=discarded_date,
        notes=notes,
    )
