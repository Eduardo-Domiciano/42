from __future__ import annotations

from app.schemas import (
    ArticleAnalysisOut,
    ClaimAssessmentOut,
    CrossReferenceOut,
    SourceOut,
    TopicPanoramaOut,
)
from app.services.bias_catalog import bias_label_pt

_VERDICT_PT = {
    "supported": "com suporte interno / apoiado pelo cruzamento",
    "disputed": "contestável",
    "insufficient": "com evidência insuficiente",
    "opinion": "tratado como opinião",
}

_STANCE_PT = {
    "supports": "apoiam",
    "refutes": "refutam",
    "related": "estão só relacionadas",
    "unrelated": "não se relacionam de forma útil",
}

_TYPE_PT = {
    "official_document": "documento oficial",
    "press_release": "comunicado",
    "opinion": "opinião",
    "editorial": "editorial",
    "analysis": "análise",
    "post": "post em rede",
    "note": "nota",
    "article": "artigo / reportagem",
}


def _verdict_pt(v: str | None) -> str:
    return _VERDICT_PT.get(v or "", v or "indefinido")


def build_article_narrative(
    *,
    title: str | None,
    source: SourceOut | None,
    analysis: ArticleAnalysisOut | None,
    claims: list[ClaimAssessmentOut],
    cross_references: list[CrossReferenceOut],
) -> str:
    paragraphs: list[str] = []
    titulo = f"“{title}”" if title else "esta matéria"

    # Fonte / bias / ownership / tipo
    if source and analysis:
        tipo = _TYPE_PT.get(analysis.content_type_guess, analysis.content_type_guess)
        ownership = analysis.ownership_name or source.ownership_name or "grupo não identificado"
        bias = bias_label_pt(analysis.bias_label or source.bias_label)
        tier = analysis.authority_tier or source.authority_tier or "desconhecido"
        p1 = (
            f"Sobre {titulo}: a fonte catalogada é {source.name}, do Ownership (grupo dono) "
            f"{ownership}, com Tier (nível de autoridade) {tier}. "
            f"O Bias (viés / parcialidade) no catálogo aponta para {bias}. "
            f"O conteúdo foi classificado como {tipo}. "
            f"{analysis.source_partiality_note} "
            f"Quanto às datas, a leitura temporal é: {analysis.temporal_coherence}."
        )
        paragraphs.append(p1)
    elif analysis:
        paragraphs.append(
            f"Sobre {titulo}: a fonte não está no catálogo BR completo. "
            f"Tipo estimado: {_TYPE_PT.get(analysis.content_type_guess, analysis.content_type_guess)}. "
            f"{analysis.source_partiality_note}"
        )
    else:
        paragraphs.append(f"Sobre {titulo}: ainda não há perfil de fonte disponível.")

    # Claims
    if claims:
        n = len(claims)
        avg_support = sum(c.score_internal_support for c in claims) / n
        avg_dist = sum(c.score_distortion for c in claims) / n
        avg_part = sum(c.score_partisan for c in claims) / n
        verdicts = {}
        for c in claims:
            verdicts[c.verdict] = verdicts.get(c.verdict, 0) + 1
        verd_txt = ", ".join(f"{_verdict_pt(k)} ({v})" for k, v in verdicts.items())
        exemplos = "; ".join(f"“{c.claim.canonical_text[:140]}”" for c in claims[:2])
        p2 = (
            f"Foram extraídos {n} Claims (afirmativas) checáveis. "
            f"Em média, o Support (suporte interno) ficou em {avg_support:.2f}, "
            f"a Distortion (distorção / risco de clickbait) em {avg_dist:.2f} e o "
            f"tom Partisan (partidário) em {avg_part:.2f}. "
            f"Distribuição de vereditos isolados (F3): {verd_txt}. "
            f"Exemplos de afirmativas: {exemplos}."
        )
        paragraphs.append(p2)
    else:
        paragraphs.append(
            "Não foram encontrados Claims (afirmativas) claramente checáveis — "
            "o texto pode ser sobretudo opinião, genérico ou curto demais para atomizar fatos."
        )

    # Cross-reference
    if cross_references:
        n = len(cross_references)
        avg_cal = sum(x.calibration_score for x in cross_references) / n
        veto = sum(1 for x in cross_references if x.primary_veto)
        same_own = sum(
            1 for x in cross_references for e in x.evidences if e.same_ownership
        )
        voices = sum(x.independent_voices for x in cross_references) / n
        cons = {}
        for x in cross_references:
            cons[x.consensus_verdict] = cons.get(x.consensus_verdict, 0) + 1
        cons_txt = ", ".join(f"{_verdict_pt(k)} ({v})" for k, v in cons.items())

        stance_bits = []
        for x in cross_references[:2]:
            supports = sum(1 for e in x.evidences if e.stance == "supports")
            refutes = sum(1 for e in x.evidences if e.stance == "refutes")
            stance_bits.append(
                f"“{x.claim_text[:100]}…” → F3 {_verdict_pt(x.isolated_verdict)}, "
                f"consenso F4 {_verdict_pt(x.consensus_verdict)} "
                f"(evidências que apoiam: {supports}, que refutam: {refutes})"
            )

        p3 = (
            f"No Cross-reference (cruzamento / F4), {n} claim(s) foram confrontados com outras fontes. "
            f"A Calibration (calibração F3 vs F4) média ficou em {avg_cal:.0%}: "
            f"valores altos significam que a leitura só do artigo bateu com o consenso externo; "
            f"valores baixos indicam divergência importante. "
            f"Consenso agregado: {cons_txt}. "
            f"Em média houve cerca de {voices:.1f} Ownership (grupo dono) independente(s) por claim."
        )
        if veto:
            p3 += (
                f" Atenção: {veto} caso(s) com Primary veto (veto de fonte oficial) — "
                f"uma fonte primária refutou a afirmativa."
            )
        if same_own:
            p3 += (
                f" Também houve {same_own} evidência(s) do mesmo Ownership da matéria original, "
                f"o que conta pouco como confirmação independente (risco de eco)."
            )
        if stance_bits:
            p3 += " Detalhe: " + " ".join(stance_bits)
        paragraphs.append(p3)
    else:
        paragraphs.append(
            "O cruzamento (F4) não trouxe evidências externas úteis neste momento — "
            "o veredito permanece dependente da análise isolada (F3). "
            "Isso pode ocorrer por falta de pares na busca, paywall ou tema muito específico."
        )

    # Fechamento
    if analysis:
        paragraphs.append(
            f"Em resumo rápido: o veredito preliminar da matéria é "
            f"“{_verdict_pt(analysis.preliminary_verdict)}” "
            f"(método {analysis.analysis_method}). "
            f"Use os detalhes acima como leitura guiada; nada disso substitui checagem humana "
            f"nem prova verdade absoluta."
        )

    return "\n\n".join(paragraphs)


def _fmt_counts(items: dict[str, int], *, label_fn) -> list[str]:
    if not items:
        return []
    return [f"{label_fn(k)} ×{v}" for k, v in items.items()]


def build_topic_narrative(
    *,
    topic: str,
    panorama: TopicPanoramaOut | None,
    articles_count: int,
) -> str:
    """Resumo geral em lista estruturada (seções + bullets), para a UI."""
    if not panorama:
        return "\n".join(
            [
                f"## Tema",
                f"- “{topic}”",
                f"## Levantamento",
                f"- {articles_count} artigo(s) retornado(s), sem panorama consolidado.",
            ]
        )

    p = panorama
    bias_items = _fmt_counts(p.bias_labels or {}, label_fn=bias_label_pt)
    type_items = _fmt_counts(
        p.content_types or {},
        label_fn=lambda k: _TYPE_PT.get(k, k),
    )
    claim_items = _fmt_counts(p.claim_verdicts or {}, label_fn=_verdict_pt)
    cons_items = _fmt_counts(p.consensus_verdicts or {}, label_fn=_verdict_pt)

    lines: list[str] = [
        "## Tema",
        f"- “{topic}”",
        "",
        "## Levantamento",
        f"- Artigos aceitos: {p.total_articles}",
        f"- Fontes distintas: {p.distinct_sources}",
        f"- Ownership (grupo dono) distintos: {p.distinct_ownerships}",
    ]
    if p.candidates_considered or p.discarded_relevance or p.discarded_date:
        lines.append(
            f"- Filtro de tema: {p.total_articles} aceito(s) de "
            f"{p.candidates_considered} candidato(s)"
            + (
                f"; {p.discarded_relevance} descartado(s) por baixa relevância"
                if p.discarded_relevance
                else ""
            )
            + (
                f"; {p.discarded_date} fora do período / sem data"
                if p.discarded_date
                else ""
            )
        )
    if bias_items:
        lines.append("- Bias (viés / parcialidade):")
        lines.extend(f"  - {item}" for item in bias_items)
    else:
        lines.append("- Bias (viés / parcialidade): sem classificação")
    if type_items:
        lines.append("- Tipos de conteúdo:")
        lines.extend(f"  - {item}" for item in type_items)
    else:
        lines.append("- Tipos de conteúdo: sem classificação")

    lines.extend(
        [
            "",
            "## Avaliação (F3 e F4)",
            f"- Claims (afirmativas) avaliados: {p.total_claims}",
        ]
    )
    if claim_items:
        lines.append("- Vereditos isolados (F3):")
        lines.extend(f"  - {item}" for item in claim_items)
    else:
        lines.append("- Vereditos isolados (F3): nenhum")
    lines.append(f"- Cross-reference (cruzamento) feitos: {p.total_cross_refs}")
    if cons_items:
        lines.append("- Consensos (F4):")
        lines.extend(f"  - {item}" for item in cons_items)
    else:
        lines.append("- Consensos (F4): nenhum cruzamento")
    if p.avg_calibration is not None:
        lines.append(
            f"- Calibration (calibração F3 vs F4) média: {p.avg_calibration:.0%}"
        )
    else:
        lines.append("- Calibration (calibração F3 vs F4) média: —")

    lines.extend(["", "## Observações"])
    # Evita repetir o filtro já listado no levantamento
    notes = [
        n
        for n in (p.notes or [])
        if not n.lower().startswith("filtro de tema:")
        and not n.lower().startswith("f4: panorama")
        and "claims (afirmativas) avaliados" not in n.lower()
        and "cruzamento(s); calibração" not in n.lower()
    ]
    if notes:
        lines.extend(f"- {n}" for n in notes[:6])
    else:
        lines.append(
            "- Síntese para leitura rápida; não é veredito final de verdade. "
            "Detalhe por matéria na lista abaixo."
        )
    lines.append(
        "- Nada disso substitui checagem humana nem prova verdade absoluta."
    )

    return "\n".join(lines)