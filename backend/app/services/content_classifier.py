from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.models import Article

# Tipos alinhados ao plano F2
CONTENT_TYPES = (
    "official_document",
    "press_release",
    "opinion",
    "editorial",
    "analysis",
    "post",
    "note",
    "article",
)


@dataclass(frozen=True)
class ContentClassification:
    content_type: str
    confidence: float
    reasons: list[str]


_OPINION = re.compile(
    r"\b(opini[aã]o|coluna|coluna\s+do|artigo\s+de\s+opini[aã]o|point\s+of\s+view)\b",
    re.I,
)
_EDITORIAL = re.compile(r"\b(editorial|nossa\s+opini[aã]o|posição\s+do\s+jornal)\b", re.I)
_ANALYSIS = re.compile(
    r"\b(an[aá]lise|explica|entenda|contexto|bastidores)\b", re.I
)
_PRESS = re.compile(
    r"\b(nota\s+oficial|comunicado|assessoria\s+de\s+imprensa|press\s+release)\b",
    re.I,
)
_NOTE = re.compile(r"\b(nota\s+da\s+reda[cç][aã]o|errata|corre[cç][aã]o)\b", re.I)
_POST = re.compile(r"(twitter\.com|x\.com|instagram\.com|facebook\.com|threads\.net)", re.I)


def classify_content(article: Article) -> ContentClassification:
    reasons: list[str] = []
    url = (article.url or "").lower()
    title = article.title or ""
    body = article.body or ""
    text_head = f"{title}\n{body[:1200]}"
    path = urlparse(url).path.lower()
    source = article.source
    kind = (source.kind if source else None) or ""
    tier = (source.authority_tier if source else None) or ""

    if _POST.search(url):
        return ContentClassification(
            "post", 0.9, ["URL de rede social"]
        )

    if kind == "government_record" or tier == "primary":
        reasons.append("Fonte oficial/primária no catálogo")
        if any(p in path for p in ("/diario", "/dou", "/portaria", "/lei", "/decreto")):
            reasons.append("Caminho de URL sugere ato normativo")
            return ContentClassification("official_document", 0.9, reasons)
        if _PRESS.search(text_head):
            reasons.append("Linguagem de comunicado")
            return ContentClassification("press_release", 0.75, reasons)
        return ContentClassification("official_document", 0.7, reasons)

    if _EDITORIAL.search(text_head) or "/editorial" in path:
        reasons.append("Sinais de editorial")
        return ContentClassification("editorial", 0.85, reasons)

    if _OPINION.search(text_head) or any(
        p in path for p in ("/opiniao", "/coluna", "/colunas", "/blogs/")
    ):
        reasons.append("Sinais de opinião/coluna")
        return ContentClassification("opinion", 0.85, reasons)

    if _NOTE.search(text_head):
        reasons.append("Nota de redação / errata")
        return ContentClassification("note", 0.8, reasons)

    if _PRESS.search(text_head):
        reasons.append("Linguagem de comunicado de imprensa")
        return ContentClassification("press_release", 0.7, reasons)

    if _ANALYSIS.search(title) or any(
        p in path for p in ("/analise", "/explica", "/contexto")
    ):
        reasons.append("Sinais de análise/explicação")
        return ContentClassification("analysis", 0.65, reasons)

    if kind == "news_article":
        reasons.append("source_kind=news_article")
        return ContentClassification("article", 0.7, reasons)

    reasons.append("Padrão: reportagem/artigo")
    return ContentClassification("article", 0.5, reasons)
