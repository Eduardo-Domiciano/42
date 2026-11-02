"""Resumos em português simples (templates; LLM opcional e desligada por padrão)."""

from __future__ import annotations

from app.config import settings
from app.schemas import (
    ArticleAnalysisOut,
    ClaimAssessmentOut,
    CrossReferenceOut,
    SourceOut,
    TopicPanoramaOut,
)
from app.services.bias_catalog import bias_label_pt
from app.services.llm_client import chat_json, llm_configured

_VERDICT_PLAIN = {
    "supported": "há respaldo interno razoável no próprio texto",
    "disputed": "há sinais de contestação ou enquadramento problemático",
    "insufficient": "a informação é apresentada com evidência insuficiente",
    "opinion": "o texto se aproxima mais de opinião do que de fato checável",
}

_VERDICT_PT = {
    "supported": "com suporte interno / apoiado pelo cruzamento",
    "disputed": "contestável",
    "insufficient": "com evidência insuficiente",
    "opinion": "tratado como opinião",
}

_TYPE_PT = {
    "official_document": "documento oficial",
    "press_release": "comunicado",
    "opinion": "opinião",
    "editorial": "editorial",
    "analysis": "análise",
    "post": "post em rede",
    "note": "nota",
    "article": "reportagem",
}

_BIAS_PLAIN = {
    "institutional": "perfil mais institucional",
    "left": "tendência à esquerda no catálogo",
    "center_left": "tendência de centro-esquerda no catálogo",
    "center": "tendência de centro no catálogo",
    "center_right": "tendência de centro-direita no catálogo",
    "right": "tendência à direita no catálogo",
    "unknown": "sem classificação clara de parcialidade no catálogo",
}


def _verdict_pt(v: str | None) -> str:
    return _VERDICT_PT.get(v or "", v or "indefinido")


def _verdict_plain(v: str | None) -> str:
    return _VERDICT_PLAIN.get(v or "", "o veredito preliminar ficou indefinido")


def _clip(text: str, n: int = 160) -> str:
    t = (text or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1].rstrip() + "…"


def _claim_f3_bullets(c: ClaimAssessmentOut) -> list[str]:
    """Notas F3 só desta afirmativa (texto legível, sem repetir a tabela)."""
    bits: list[str] = []
    if c.score_internal_support >= 0.55 and c.score_distortion <= 0.45:
        bits.append(
            "Traz algum respaldo no próprio texto (números, citações ou links)."
        )
    elif c.score_internal_support < 0.4:
        bits.append(
            "Aparece mais como afirmação, sem evidência clara no próprio texto."
        )
    else:
        bits.append("Tem respaldo parcial no texto.")

    if c.score_temporal < 0.4:
        bits.append("Fica vaga quanto ao momento em que isso teria ocorrido.")
    if c.score_geographic < 0.4:
        bits.append("Pouca âncora de lugar ou instituição no trecho.")
    if c.score_partisan >= 0.55:
        bits.append("Carrega tom partidário ou polarizado.")
    if c.score_distortion >= 0.55:
        bits.append("Há risco de exagero ou título pouco alinhado ao conteúdo.")
    if c.verdict == "opinion":
        bits.append("Soa sobretudo como opinião.")
    elif c.verdict == "disputed":
        bits.append("A leitura isolada (F3) aponta contestação ou tensão no texto.")
    elif c.verdict == "supported":
        bits.append("A leitura isolada (F3) encontra suporte interno razoável.")
    elif c.verdict == "insufficient":
        bits.append(
            "A leitura isolada (F3) considera a evidência insuficiente para "
            "fechar o ponto."
        )
    return bits


def _claim_f4_bullets(x: CrossReferenceOut | None) -> list[str]:
    """Notas F4 só desta afirmativa."""
    if x is None:
        return [
            "Não houve cruzamento com outras matérias para esta afirmativa "
            "(poucos resultados ou cruzamento não rodou)."
        ]
    supports = sum(1 for e in x.evidences if e.stance == "supports")
    refutes = sum(1 for e in x.evidences if e.stance == "refutes")
    related = sum(1 for e in x.evidences if e.stance == "related")
    bits: list[str] = []
    bits.append(
        f"Em outras publicações: {supports} sinal(is) na mesma direção, "
        f"{refutes} em sentido contrário"
        + (f", {related} só relacionados" if related else "")
        + "."
    )
    cons = x.consensus_verdict or ""
    if cons == "supported" and supports > refutes:
        bits.append(
            "Há alguma coincidência com outras publicações, o que aumenta a "
            "confiança nesta afirmativa, mas ainda não fecha o caso como "
            "verdade absoluta."
        )
    elif cons == "disputed" or refutes > supports:
        bits.append(
            "O que esta afirmativa diz não encontra coro tranquilo do lado "
            "de fora — há mais discordância ou outra versão."
        )
    elif supports == 0 and refutes == 0:
        bits.append(
            "O cenário externo ficou nebuloso: poucas matérias úteis para "
            "confirmar ou desmentir esta afirmativa."
        )
    else:
        bits.append(
            f"Consenso do cruzamento: {_verdict_pt(cons)}; "
            f"alinhamento F3×F4 cerca de {x.calibration_score:.0%}."
        )
    if x.primary_veto:
        bits.append(
            "Há veto de fonte oficial/primária no cruzamento — trate com "
            "mais cautela."
        )
    if x.independent_voices <= 1 and (supports + refutes) > 0:
        bits.append(
            "Poucas vozes independentes (pode haver concentração de ownership)."
        )
    return bits


def _xref_for_claim(
    claim_id: int, cross_references: list[CrossReferenceOut]
) -> CrossReferenceOut | None:
    for x in cross_references:
        if x.claim_id == claim_id:
            return x
    return None


def build_article_narrative_plain(
    *,
    title: str | None,
    source: SourceOut | None,
    analysis: ArticleAnalysisOut | None,
    claims: list[ClaimAssessmentOut],
    cross_references: list[CrossReferenceOut],
) -> str:
    """Resumo por afirmativa: texto da claim + bullets F3/F4 (sem nota geral)."""
    paragraphs: list[str] = []
    if source and source.name:
        fonte_frase = f"do {source.name}"
    else:
        fonte_frase = "de um veículo ainda não catalogado"
    titulo = _clip(title or "esta matéria", 140)
    tipo = "reportagem"
    if analysis:
        tipo = _TYPE_PT.get(analysis.content_type_guess, "matéria")

    bias_key = None
    if analysis:
        bias_key = analysis.bias_label
    elif source:
        bias_key = source.bias_label
    bias_txt = _BIAS_PLAIN.get(bias_key or "unknown", _BIAS_PLAIN["unknown"])

    if bias_key in (None, "unknown"):
        bias_clause = f"Parcialidade do veículo: {bias_txt}."
    else:
        bias_clause = f"O veículo costuma ter {bias_txt}."
    paragraphs.append(
        "Resumo por afirmativa\n"
        f"Esta {tipo} {fonte_frase}, “{titulo}”. {bias_clause}"
    )

    if not claims:
        paragraphs.append(
            "Não apareceu frase clara o bastante para ser checada "
            "(texto curto, genérico ou bem opinativo)."
        )
    else:
        for i, c in enumerate(claims, start=1):
            claim_txt = (c.claim.canonical_text if c.claim else "").strip() or (
                "(sem texto)"
            )
            lines = [f"{i}. {claim_txt}"]
            for note in _claim_f3_bullets(c):
                lines.append(f"- {note}")
            xref = _xref_for_claim(c.claim.id if c.claim else -1, cross_references)
            for note in _claim_f4_bullets(xref):
                lines.append(f"- {note}")
            paragraphs.append("\n".join(lines))

    closing = (
        "Nada disso substitui o seu julgamento nem uma checagem humana "
        "mais profunda: pense neste texto como um guia de leitura — "
        "o que cada afirmativa mostra, o que omite e o que outras vozes "
        "dizem a respeito."
    )
    if analysis and analysis.source_partiality_note:
        note = analysis.source_partiality_note.strip()
        if note and len(note) < 200:
            closing = f"{note}\n\n{closing}"
    paragraphs.append(closing)

    return "\n\n".join(paragraphs)


def build_article_narrative_technical(
    *,
    title: str | None,
    source: SourceOut | None,
    analysis: ArticleAnalysisOut | None,
    claims: list[ClaimAssessmentOut],
    cross_references: list[CrossReferenceOut],
) -> str:
    """Versão antiga com jargão — mantida só se alguém quiser depurar."""
    paragraphs: list[str] = []
    titulo = f"“{title}”" if title else "esta matéria"
    if source and analysis:
        tipo = _TYPE_PT.get(analysis.content_type_guess, analysis.content_type_guess)
        ownership = (
            analysis.ownership_name or source.ownership_name or "grupo não identificado"
        )
        bias = bias_label_pt(analysis.bias_label or source.bias_label)
        paragraphs.append(
            f"Sobre {titulo}: fonte {source.name}, ownership {ownership}, "
            f"bias {bias}, tipo {tipo}. {analysis.source_partiality_note} "
            f"Temporal: {analysis.temporal_coherence}."
        )
    if claims:
        n = len(claims)
        avg_s = sum(c.score_internal_support for c in claims) / n
        paragraphs.append(
            f"{n} claim(s); suporte médio {avg_s:.2f}. "
            + "; ".join(f"“{_clip(c.claim.canonical_text, 80)}”" for c in claims[:2])
        )
    if cross_references:
        paragraphs.append(f"{len(cross_references)} cruzamento(s) F4.")
    if analysis:
        paragraphs.append(
            f"Veredito preliminar: {_verdict_pt(analysis.preliminary_verdict)}."
        )
    return "\n\n".join(paragraphs) if paragraphs else "Sem resumo."


def _humanize_with_llm(facts: str) -> str | None:
    if not settings.narrative_use_llm or not llm_configured():
        return None
    data = chat_json(
        "Escreva 2-4 parágrafos em português simples. JSON: {\"summary\":\"...\"}",
        "FATOS:\n" + facts[:3500],
        temperature=0.3,
        model=settings.narrative_llm_model or settings.local_llm_model or None,
        timeout=settings.narrative_llm_timeout,
    )
    if not data:
        return None
    summary = data.get("summary")
    return summary.strip() if isinstance(summary, str) and summary.strip() else None


def build_article_narrative(
    *,
    title: str | None,
    source: SourceOut | None,
    analysis: ArticleAnalysisOut | None,
    claims: list[ClaimAssessmentOut],
    cross_references: list[CrossReferenceOut],
    allow_llm: bool = True,
) -> str:
    plain = build_article_narrative_plain(
        title=title,
        source=source,
        analysis=analysis,
        claims=claims,
        cross_references=cross_references,
    )
    if allow_llm and settings.narrative_use_llm and llm_configured():
        human = _humanize_with_llm(plain)
        if human:
            return human
    return plain


def _fmt_counts(items: dict[str, int], *, label_fn) -> list[str]:
    if not items:
        return []
    return [f"{label_fn(k)} ×{v}" for k, v in items.items()]


def build_topic_narrative_technical(
    *,
    topic: str,
    panorama: TopicPanoramaOut | None,
    articles_count: int,
) -> str:
    if not panorama:
        return "\n".join(
            [
                "## Tema",
                f"- “{topic}”",
                "## Levantamento",
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
        f"- Grupos donos distintos: {p.distinct_ownerships}",
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
        lines.append("- Viés / parcialidade:")
        lines.extend(f"  - {item}" for item in bias_items)
    if type_items:
        lines.append("- Tipos de conteúdo:")
        lines.extend(f"  - {item}" for item in type_items)

    lines.extend(
        [
            "",
            "## Avaliação (Afirmativas e referencias cruzadas)",
            f"- Afirmativas avaliadas: {p.total_claims}",
        ]
    )
    if claim_items:
        lines.append("- Vereditos isolados:")
        lines.extend(f"  - {item}" for item in claim_items)
    lines.append(f"- Referencias-cruzadas: {p.total_cross_refs}")
    if cons_items:
        lines.append("- Consensos entre fontes:")
        lines.extend(f"  - {item}" for item in cons_items)
    if p.avg_calibration is not None:
        lines.append(f"- Alinhamento artigo×outras fontes (média): {p.avg_calibration:.0%}")

    lines.extend(
        [
            "",
            "## Observações",
            "- Síntese para leitura rápida; não é veredito final de verdade.",
            "- Nada disso substitui checagem humana nem prova verdade absoluta.",
        ]
    )
    return "\n".join(lines)


def build_topic_narrative_plain(
    *,
    topic: str,
    panorama: TopicPanoramaOut | None,
    articles_count: int,
) -> str:
    """Parágrafo humanizado + detalhe estruturado para a UI do tema."""
    if not panorama:
        prose = (
            f"Em termos simples: a busca por “{topic}” trouxe {articles_count} "
            f"matéria(s), mas ainda não deu para montar um panorama claro — "
            f"faltou variedade de fontes ou o tema veio muito estreito. Vale "
            f"abrir os textos um a um e ler com calma."
        )
        return "\n\n".join([prose])

    p = panorama
    prose = (
        f"Em termos simples: ao procurar “{topic}”, a ferramenta reuniu "
        f"{p.total_articles} matéria(s) de {p.distinct_sources} veículo(s) "
        f"diferentes ({p.distinct_ownerships} grupo(s) de mídia). Em cada "
        f"texto, ela separou o que dá para checar e olhou se outras "
        f"publicações confirmam ou discordam — no total, "
        f"{p.total_claims} ideia(s) checável(is) e {p.total_cross_refs} "
        f"comparação(ões) com o restante da imprensa."
    )
    if p.discarded_relevance:
        prose += (
            f" Alguns candidatos ({p.discarded_relevance}) ficaram de fora "
            f"porque pareciam só de passagem no assunto, não o foco da pauta."
        )
    if p.avg_calibration is not None:
        prose += (
            f" Em média, o que cada artigo diz e o que outras fontes mostram "
            f"coincidem em cerca de {p.avg_calibration:.0%} — um termômetro "
            f"grosseiro de alinhamento, não um carimbo de verdade."
        )
    prose += (
        " Use este panorama como mapa de leitura: ele aponta caminhos, "
        "mas não substitui o seu julgamento."
    )

    technical = build_topic_narrative_technical(
        topic=topic, panorama=panorama, articles_count=articles_count
    )
    return "\n\n".join([prose, technical])


def build_topic_narrative(
    *,
    topic: str,
    panorama: TopicPanoramaOut | None,
    articles_count: int,
    allow_llm: bool = True,
) -> str:
    return build_topic_narrative_plain(
        topic=topic, panorama=panorama, articles_count=articles_count
    )
