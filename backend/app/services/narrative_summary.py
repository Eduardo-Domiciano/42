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


def _claim_plain_note(c: ClaimAssessmentOut) -> str:
    bits: list[str] = []
    if c.score_internal_support >= 0.55 and c.score_distortion <= 0.45:
        bits.append("traz algum respaldo no próprio texto (números, citações ou links)")
    elif c.score_internal_support < 0.4:
        bits.append("aparece mais como afirmação, sem evidência clara no texto")
    else:
        bits.append("tem respaldo parcial no texto")

    if c.score_temporal < 0.4:
        bits.append("fica vaga quanto ao momento em que isso teria ocorrido")
    if c.score_partisan >= 0.55:
        bits.append("carrega tom partidário ou polarizado")
    if c.score_distortion >= 0.55:
        bits.append("há risco de exagero ou título pouco alinhado ao conteúdo")
    if c.verdict == "opinion":
        bits.append("soa sobretudo como opinião")
    return "; ".join(bits)


def build_article_narrative_plain(
    *,
    title: str | None,
    source: SourceOut | None,
    analysis: ArticleAnalysisOut | None,
    claims: list[ClaimAssessmentOut],
    cross_references: list[CrossReferenceOut],
) -> str:
    """Prosa humana por regras — próximo do resumo que a LLM gerava."""
    paragraphs: list[str] = []
    fonte = source.name if source else "uma fonte não catalogada"
    titulo = _clip(title or "Sem título", 140)
    tipo = "reportagem"
    if analysis:
        tipo = _TYPE_PT.get(analysis.content_type_guess, "matéria")

    # §1 — o que a matéria aborda
    if claims:
        lead_claim = _clip(claims[0].claim.canonical_text, 180)
        p1 = (
            f"O artigo do {fonte} ({tipo}) trata de “{titulo}”. "
            f"Entre as afirmativas que a análise destacou está: “{lead_claim}”."
        )
    else:
        p1 = (
            f"O artigo do {fonte} ({tipo}) trata de “{titulo}”. "
            f"Não foi possível extrair afirmativas claramente checáveis — "
            f"o texto pode ser genérico, curto ou predominantemente opinativo."
        )
    if analysis and analysis.source_partiality_note:
        note = analysis.source_partiality_note.strip()
        if note and len(note) < 220:
            p1 += f" {note}"
    paragraphs.append(p1)

    # §2 — afirmativas em linguagem simples
    if len(claims) >= 1:
        parts: list[str] = []
        for c in claims[:3]:
            txt = _clip(c.claim.canonical_text, 120)
            parts.append(f"“{txt}” ({_claim_plain_note(c)})")
        if len(claims) == 1:
            p2 = f"A principal afirmativa observada é {parts[0]}."
        else:
            joined = "; ".join(parts[:-1])
            p2 = (
                f"A matéria destaca estas afirmativas: {joined}; "
                f"e ainda {parts[-1]}."
            )
        weak = [c for c in claims if c.score_internal_support < 0.4]
        strong = [
            c
            for c in claims
            if c.score_internal_support >= 0.55 and c.score_distortion <= 0.45
        ]
        if weak and strong:
            p2 += (
                " Em resumo: algumas passam a impressão de ter base no texto, "
                "enquanto outras só afirmam, sem evidência que corrobore."
            )
        elif weak and not strong:
            p2 += (
                " No conjunto, prevalecem trechos que afirmam sem apresentar "
                "evidência concreta no próprio artigo — muitas vezes só opinião "
                "ou fala de especialistas sem dado verificável ao lado."
            )
        elif strong and not weak:
            p2 += (
                " No conjunto, as afirmativas trazem algum lastro interno "
                "(números, citações ou referências no texto)."
            )
        paragraphs.append(p2)

    # §3 — cruzamento / outras fontes
    if cross_references:
        supports = sum(
            1 for x in cross_references for e in x.evidences if e.stance == "supports"
        )
        refutes = sum(
            1 for x in cross_references for e in x.evidences if e.stance == "refutes"
        )
        n = len(cross_references)
        links = []
        for x in cross_references[:2]:
            for e in x.evidences[:2]:
                if e.article_url and e.article_url not in links:
                    links.append(e.article_url)
        p3 = (
            f"Ao confrontar {n} afirmativa(s) com outras matérias, "
            f"apareceram {supports} trecho(s) que apontam na mesma direção "
            f"e {refutes} que contestam ou contradizem."
        )
        if refutes > supports:
            p3 += (
                " As fontes consultadas, no geral, não bastam para confirmar "
                "as afirmativas — há mais contestação do que respaldo externo."
            )
        elif supports > refutes and supports > 0:
            p3 += (
                " Há algum eco em outras publicações, mas isso ainda não prova "
                "verdade absoluta — só indica convergência parcial."
            )
        else:
            p3 += (
                " O cruzamento ficou pouco conclusivo: poucas evidências "
                "externas úteis para confirmar ou refutar."
            )
        if links:
            shown = ", ".join(links[:3])
            p3 += f" Fontes usadas no cruzamento incluem: {shown}."
        paragraphs.append(p3)
    else:
        paragraphs.append(
            "Não houve cruzamento útil com outras matérias neste momento "
            "(falta de pares na busca, paywall ou tema muito específico). "
            "A leitura fica dependente só do que está neste artigo."
        )

    # §4 — tom + veredito acessível
    bias_key = None
    if analysis:
        bias_key = analysis.bias_label
    elif source:
        bias_key = source.bias_label
    bias_txt = _BIAS_PLAIN.get(bias_key or "unknown", _BIAS_PLAIN["unknown"])

    closing = (
        f"O título sugere o enquadramento da pauta; a fonte tem {bias_txt}. "
    )
    if analysis:
        closing += (
            f"Pela análise automática, {_verdict_plain(analysis.preliminary_verdict)}. "
        )
    closing += (
        "Isso é uma leitura guiada para o leitor comum — "
        "não substitui checagem humana nem prova verdade absoluta."
    )
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
    """Um parágrafo humano + lista estruturada para a UI do tema."""
    if not panorama:
        prose = (
            f"Sobre o tema “{topic}”, a busca devolveu {articles_count} artigo(s), "
            f"sem panorama consolidado o bastante para um resumo mais fino."
        )
        return "\n".join(["## Em linguagem simples", f"- {prose}", ""])

    p = panorama
    prose = (
        f"Sobre “{topic}”, entraram {p.total_articles} matéria(s) de "
        f"{p.distinct_sources} fonte(s) ({p.distinct_ownerships} grupo(s) dono distintos). "
        f"Foram avaliadas {p.total_claims} afirmativa(s) e feitos "
        f"{p.total_cross_refs} cruzamento(s) com outras publicações."
    )
    if p.discarded_relevance:
        prose += (
            f" O filtro deixou de fora {p.discarded_relevance} candidato(s) "
            f"por parecerem pouco ligados ao tema."
        )
    if p.avg_calibration is not None:
        prose += (
            f" Em média, o alinhamento entre o que o artigo diz e o que outras "
            f"fontes mostram ficou em {p.avg_calibration:.0%}."
        )
    prose += " Leitura guiada — não é veredito final."

    technical = build_topic_narrative_technical(
        topic=topic, panorama=panorama, articles_count=articles_count
    )
    return "\n".join(["## Em linguagem simples", f"- {prose}", "", technical])


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
