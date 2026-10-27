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
    """Resumo em prosa acessível — pelo menos um parágrafo bem humanizado."""
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

    # §1 — parágrafo de abertura, linguagem do dia a dia
    if claims:
        lead = _clip(claims[0].claim.canonical_text, 160)
        opening = (
            f"Em termos simples: esta {tipo} {fonte_frase}, intitulada “{titulo}”, "
            f"conta uma história centrada na ideia de que “{lead}”. "
            f"A ferramenta leu o texto do começo ao fim, procurou o que dá para "
            f"checar com calma e depois olhou se outras publicações dizem a mesma "
            f"coisa ou discordam — tudo para ajudar quem não acompanha o jargão "
            f"técnico a formar uma opinião mais segura."
        )
    else:
        opening = (
            f"Em termos simples: esta {tipo} {fonte_frase}, intitulada “{titulo}”, "
            f"foi lida pela ferramenta, mas quase não apareceu frase clara o "
            f"bastante para ser checada (texto curto, genérico ou bem opinativo). "
            f"Ainda assim vale ler o que segue com atenção: o tom da fonte e o "
            f"que falta de base no texto também dizem bastante sobre a matéria."
        )
    if analysis:
        opening += (
            f" De cara, a leitura automática sugere que "
            f"{_verdict_plain(analysis.preliminary_verdict)}, "
            f"e o veículo costuma ter {bias_txt}."
        )
    else:
        opening += f" O veículo costuma ter {bias_txt}."
    paragraphs.append(opening)

    # §2 — o que a matéria afirma, sem jargão
    if claims:
        weak = [c for c in claims if c.score_internal_support < 0.4]
        strong = [
            c
            for c in claims
            if c.score_internal_support >= 0.55 and c.score_distortion <= 0.45
        ]
        samples: list[str] = []
        for c in claims[:3]:
            txt = _clip(c.claim.canonical_text, 110)
            samples.append(f"“{txt}” ({_claim_plain_note(c)})")
        if len(samples) == 1:
            p2 = f"O ponto principal que saltou do texto é {samples[0]}."
        else:
            p2 = (
                "Entre as ideias que a matéria coloca na mesa estão "
                + "; ".join(samples[:-1])
                + f"; e também {samples[-1]}."
            )
        if weak and not strong:
            p2 += (
                " No geral, o texto pede que a gente acredite sem mostrar bem "
                "de onde veio o número, a citação ou a prova — o que deixa a "
                "história mais frágil para quem quer conferir."
            )
        elif strong and not weak:
            p2 += (
                " Em vários trechos há números, falas ou referências dentro "
                "da própria matéria, o que ajuda a acompanhar o raciocínio "
                "mesmo sem ser especialista."
            )
        elif weak and strong:
            p2 += (
                " Há um pouco de cada: partes com alguma base no texto e "
                "outras que soam mais como opinião solta."
            )
        paragraphs.append(p2)

    # §3 — o que outras fontes disseram
    if cross_references:
        supports = sum(
            1 for x in cross_references for e in x.evidences if e.stance == "supports"
        )
        refutes = sum(
            1 for x in cross_references for e in x.evidences if e.stance == "refutes"
        )
        p3 = (
            f"Quando a mesma história foi procurada em outras matérias, "
            f"surgiram {supports} sinal(is) na mesma direção e {refutes} "
            f"que puxam para o lado contrário."
        )
        if refutes > supports:
            p3 += (
                " Ou seja: o que esta reportagem afirma não encontra um "
                "coro tranquilo do lado de fora — há mais gente discordando "
                "ou apontando outra versão."
            )
        elif supports > refutes and supports > 0:
            p3 += (
                " Há alguma coincidência com outras publicações, o que "
                "aumenta a confiança na leitura, mas ainda não fecha o "
                "caso como verdade absoluta."
            )
        else:
            p3 += (
                " O cenário externo ficou meio nebuloso: poucas matérias "
                "úteis para confirmar ou desmentir com segurança."
            )
        paragraphs.append(p3)
    else:
        paragraphs.append(
            "Desta vez não deu para cruzar bem com outras reportagens "
            "(poucos resultados, página bloqueada ou assunto muito "
            "específico). Por isso a leitura depende sobretudo do que "
            "está escrito nesta própria matéria."
        )

    # §4 — fechamento amigável
    closing = (
        "Nada disso substitui o seu julgamento nem uma checagem humana "
        "mais profunda: pense neste texto como um guia de leitura — "
        "uma conversa franca sobre o que a matéria mostra, o que omite "
        "e o que outras vozes dizem a respeito."
    )
    if analysis and analysis.source_partiality_note:
        note = analysis.source_partiality_note.strip()
        if note and len(note) < 200:
            closing = f"{note} {closing}"
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
