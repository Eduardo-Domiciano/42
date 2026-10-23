from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from app.models import Article

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n+")
_OPINION = re.compile(
    r"\b(acho|creio|parece|deveria|lamentável|absurdo|vergonha|na minha opinião|"
    r"é preciso|precisa-se|oxalá)\b",
    re.I,
)
_FACTISH = re.compile(
    r"\b(\d+|%|r\$|aprovou|anunciou|disse|afirmou|segundo|conforme|divulgou|"
    r"publicou|aumentou|caiu|cresceu|morreu|eleito|nomeou|vetou|sancionou)\b",
    re.I,
)
_DATE = re.compile(
    r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?\s+\d{4}|"
    r"(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|"
    r"novembro|dezembro)\s+de\s+\d{4})\b",
    re.I,
)
_BR_PLACE = re.compile(
    r"\b(brasil|brasília|são paulo|rio de janeiro|minas gerais|bahia|pernambuco|"
    r"paraná|rio grande do sul|ceará|goiás|amazonas|pará|santa catarina|"
    r"distrito federal|sp|rj|mg|df|stf|stj|congresso|planalto|senado|câmara)\b",
    re.I,
)
_PARTISAN = re.compile(
    r"\b(lula|bolsonaro|pt\b|pl\b|mdb|psdb|psol|união brasil|esquerda|direita|"
    r"petista|bolsonarista|golpista|comunista|fascista|militante)\b",
    re.I,
)
_SENSATIONAL = re.compile(
    r"\b(chocante|bombástico|urgente|você não vai acreditar|escândalo|implode|"
    r"destrói|humilha|em pânico)\b",
    re.I,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?|R\$\s*\d")
_QUOTE = re.compile(r"[\"“”'].{10,}?[\"“”']")
_URL = re.compile(r"https?://\S+")


@dataclass
class RawClaim:
    text: str
    checkability: str  # checkable | opinion | unclear
    entities: list[str] = field(default_factory=list)
    time_scope: str | None = None
    place_scope: str | None = None


@dataclass
class ClaimScores:
    temporal: float
    geographic: float
    partisan: float  # 0 = neutro, 1 = muito partidário
    distortion: float  # 0 = pouco, 1 = muita distorção
    internal_support: float
    verdict: str
    confidence: float
    justification: str
    factors: list[str]
    excerpts: list[str]


def normalize_claim_text(text: str) -> str:
    """Minúsculas, sem acento/pontuação — base do fingerprint e near-dup."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFD", text.strip().lower())
    norm = "".join(c for c in norm if unicodedata.category(c) != "Mn")
    norm = re.sub(r"[^\w\s]", " ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_claim_text(text).encode("utf-8")).hexdigest()[:32]


def _claim_tokens(text: str) -> set[str]:
    return {t for t in normalize_claim_text(text).split() if len(t) >= 3}


def claims_near_duplicate(a: str, b: str, *, jaccard: float = 0.72) -> bool:
    """True se duas frases são a mesma afirmativa (idênticas ou quase)."""
    na, nb = normalize_claim_text(a), normalize_claim_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 36 and shorter in longer and len(shorter) / len(longer) >= 0.68:
        return True
    ta, tb = _claim_tokens(na), _claim_tokens(nb)
    if len(ta) < 3 or len(tb) < 3:
        return False
    return len(ta & tb) / len(ta | tb) >= jaccard


def extract_claims_heuristic(article: Article, limit: int = 6) -> list[RawClaim]:
    title = (article.title or "").strip()
    body = (article.body or "").strip()
    blob = f"{title}. {body}" if title else body
    if not blob:
        return []

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(blob) if s and len(s.strip()) > 40]
    # Prioriza título
    if title and len(title) > 20:
        sentences = [title] + [s for s in sentences if s.lower() != title.lower()]

    claims: list[RawClaim] = []
    seen: set[str] = set()
    for sent in sentences:
        if len(claims) >= limit:
            break
        fp = fingerprint(sent)
        if fp in seen:
            continue
        if any(claims_near_duplicate(sent, c.text) for c in claims):
            continue
        seen.add(fp)

        if _OPINION.search(sent) and not _FACTISH.search(sent):
            checkability = "opinion"
        elif _FACTISH.search(sent) or _DATE.search(sent) or _NUMBER.search(sent):
            checkability = "checkable"
        else:
            checkability = "unclear"

        if checkability == "opinion":
            continue

        entities = list({m.group(0) for m in _BR_PLACE.finditer(sent)})[:8]
        dates = [m.group(0) for m in _DATE.finditer(sent)]
        claims.append(
            RawClaim(
                text=sent[:500],
                checkability=checkability,
                entities=entities,
                time_scope=dates[0] if dates else None,
                place_scope=", ".join(entities[:3]) if entities else None,
            )
        )
    return claims


def score_claim_heuristic(article: Article, claim: RawClaim) -> ClaimScores:
    text = claim.text
    title = article.title or ""
    body = article.body or ""
    factors: list[str] = []
    excerpts: list[str] = []

    # Temporal: presença de data + coerência com published_at
    temporal = 0.45
    if _DATE.search(text) or _DATE.search(body[:800]):
        temporal += 0.25
        factors.append("Há referência temporal no texto")
        m = _DATE.search(text) or _DATE.search(body[:800])
        if m:
            excerpts.append(m.group(0))
    if article.published_at:
        temporal += 0.15
        factors.append("Artigo tem published_at")
    else:
        temporal -= 0.1
        factors.append("Sem data de publicação do artigo")
    temporal = max(0.0, min(1.0, temporal))

    # Geográfico / entidades BR
    geo_hits = list(_BR_PLACE.finditer(text)) + list(_BR_PLACE.finditer(body[:1000]))
    geographic = min(1.0, 0.35 + 0.15 * len(geo_hits))
    if geo_hits:
        factors.append(f"Local/entidade BR: {geo_hits[0].group(0)}")
        excerpts.append(geo_hits[0].group(0))
    else:
        factors.append("Pouca âncora geográfica/institucional BR no claim")
        geographic = 0.3

    # Partidário (alto = mais framing político)
    part_hits = list(_PARTISAN.finditer(f"{title}\n{text}\n{body[:800]}"))
    partisan = min(1.0, 0.15 + 0.2 * len(part_hits))
    if part_hits:
        factors.append(f"Sinais partidários/políticos: {part_hits[0].group(0)}")
    else:
        factors.append("Poucos marcadores partidários explícitos no trecho")
        partisan = 0.2

    # Distorção / clickbait título vs corpo
    distortion = 0.25
    if _SENSATIONAL.search(title):
        distortion += 0.35
        factors.append("Título com linguagem sensacionalista")
    title_tokens = {t for t in re.findall(r"\w{4,}", title.lower())}
    body_tokens = {t for t in re.findall(r"\w{4,}", body[:1500].lower())}
    if title_tokens and body_tokens:
        overlap = len(title_tokens & body_tokens) / max(len(title_tokens), 1)
        if overlap < 0.15:
            distortion += 0.3
            factors.append("Baixa sobreposição título/corpo (possível clickbait)")
        else:
            factors.append(f"Sobreposição título/corpo ~{overlap:.0%}")
            distortion = max(0.15, distortion - 0.1)
    distortion = max(0.0, min(1.0, distortion))

    # Complemento NN: clickbait semântico título×corpo (se pacotes/modelos ok)
    from app.services.nn_clickbait import blend_distortion

    distortion, nn_note = blend_distortion(distortion, title, body)
    if nn_note:
        factors.append(nn_note)

    # Suporte factual interno
    support = 0.2
    if _NUMBER.search(text) or _NUMBER.search(body[:1200]):
        support += 0.25
        factors.append("Há números/percentuais no texto")
    if _QUOTE.search(body[:2000]):
        support += 0.25
        factors.append("Há citações entre aspas")
        q = _QUOTE.search(body[:2000])
        if q:
            excerpts.append(q.group(0)[:180])
    if _URL.search(body):
        support += 0.2
        factors.append("Há links no corpo")
    if claim.checkability == "checkable":
        support += 0.1
    support = max(0.0, min(1.0, support))

    # Veredito isolado (sem cruzamento externo)
    if claim.checkability == "opinion":
        verdict = "opinion"
        confidence = 0.7
    elif support >= 0.55 and temporal >= 0.5 and distortion <= 0.45:
        verdict = "insufficient"  # parece checável e internamente ok, falta F4
        confidence = 0.45
        factors.append("Claim checável com suporte interno moderado — falta cruzamento (F4)")
    elif distortion >= 0.65 or partisan >= 0.7:
        verdict = "disputed"
        confidence = 0.4
        factors.append("Sinais de framing/distorção elevam disputa do claim")
    else:
        verdict = "insufficient"
        confidence = 0.35
        factors.append("Evidência interna incompleta para afirmar suporte")

    justification = (
        f"Scores heurísticos F3 — temporal={temporal:.2f}, geo={geographic:.2f}, "
        f"partidário={partisan:.2f}, distorção={distortion:.2f}, "
        f"suporte_interno={support:.2f}."
    )
    return ClaimScores(
        temporal=round(temporal, 3),
        geographic=round(geographic, 3),
        partisan=round(partisan, 3),
        distortion=round(distortion, 3),
        internal_support=round(support, 3),
        verdict=verdict,
        confidence=round(confidence, 3),
        justification=justification,
        factors=factors,
        excerpts=excerpts[:4],
    )
