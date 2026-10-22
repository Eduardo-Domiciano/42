from __future__ import annotations

import re

from app.models import Article
from app.services.llm_client import chat_json, llm_configured
from app.services.nn_nli import stance_nli

_NEGATION = re.compile(
    r"\b(não|nao|jamais|nunca|falso|mentira|desment|nega|negou|sem comprov|"
    r"não confirma|nao confirma|boato)\b",
    re.I,
)
_SUPPORT = re.compile(
    r"\b(confirm|comprova|segundo|conforme|anunciou|aprovou|divulgou|"
    r"oficial|de acordo)\b",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w{4,}", (text or "").lower()) if t}


def stance_heuristic(claim_text: str, evidence: Article) -> tuple[str, float, str]:
    """Retorna (stance, confidence, note)."""
    blob = f"{evidence.title or ''}\n{(evidence.body or '')[:2500]}"
    claim_toks = _tokens(claim_text)
    evid_toks = _tokens(blob)
    if not claim_toks or not evid_toks:
        return "unrelated", 0.2, "Pouco texto para comparar"

    overlap = len(claim_toks & evid_toks) / max(len(claim_toks), 1)
    if overlap < 0.12:
        return "unrelated", 0.35, f"Baixa sobreposição lexical ({overlap:.0%})"

    has_neg = bool(_NEGATION.search(blob))
    has_sup = bool(_SUPPORT.search(blob))

    if has_neg and overlap >= 0.2:
        return "refutes", 0.55, "Sobreposição com marcadores de negação/desmentido"
    if has_sup and overlap >= 0.2:
        return "supports", 0.55, "Sobreposição com marcadores de confirmação"
    if overlap >= 0.35:
        return "related", 0.5, f"Mesmo tema provável (overlap {overlap:.0%})"
    return "related", 0.4, f"Relacionado fracamente (overlap {overlap:.0%})"


def stance_llm(claim_text: str, evidence: Article) -> tuple[str, float, str] | None:
    if not llm_configured():
        return None
    body = (evidence.body or "")[:2000]
    data = chat_json(
        "Classifique a relação entre um claim e um texto de evidência. "
        "JSON: {\"stance\":\"supports|refutes|related|unrelated\",\"confidence\":0.0,\"note\":\"...\"}",
        f"Claim: {claim_text}\n\nEvidência título: {evidence.title}\n\nEvidência:\n{body}",
    )
    if not data:
        return None
    stance = str(data.get("stance") or "related")
    if stance not in {"supports", "refutes", "related", "unrelated"}:
        stance = "related"
    try:
        conf = float(data.get("confidence") or 0.5)
    except (TypeError, ValueError):
        conf = 0.5
    note = str(data.get("note") or "Stance via LLM")
    return stance, conf, note


def _merge_heuristic_nli(
    h_stance: str,
    h_conf: float,
    h_note: str,
    n_stance: str,
    n_conf: float,
    n_note: str,
) -> tuple[str, float, str]:
    """Fusão complementar: NLI reforça ou atenua a heurística; não a apaga."""
    hard = {"supports", "refutes"}

    if n_stance == h_stance:
        conf = min(0.99, (h_conf + n_conf) / 2.0 + 0.08)
        note = f"{h_note} | {n_note} (concordam)"
        return h_stance, conf, note

    if {h_stance, n_stance} <= hard:
        # Discordância forte: baixa confiança; se NLI bem mais certa, segue NLI
        if n_conf >= h_conf + 0.18:
            stance = n_stance
        elif h_conf >= n_conf + 0.18:
            stance = h_stance
        else:
            stance = "related"
        conf = max(0.12, min(h_conf, n_conf) * 0.65)
        note = (
            f"Heurística={h_stance} ({h_conf:.2f}) vs NLI={n_stance} ({n_conf:.2f}); "
            f"{h_note} | {n_note}"
        )
        return stance, conf, note

    # Preferir sinal hard quando o outro é related/unrelated
    if h_stance in hard and n_stance not in hard:
        if h_conf >= 0.45:
            return h_stance, h_conf, f"{h_note} | NLI={n_stance}: {n_note}"
    if n_stance in hard and h_stance not in hard:
        if n_conf >= 0.45:
            conf = min(0.9, (h_conf + n_conf) / 2.0)
            return n_stance, conf, f"{h_note} | {n_note}"

    if h_stance == "unrelated" and n_stance == "related":
        return "related", max(0.35, (h_conf + n_conf) / 2.0), f"{h_note} | {n_note}"
    if n_stance == "unrelated" and h_stance == "related":
        return "related", max(0.3, h_conf * 0.85), f"{h_note} | {n_note}"

    conf = max(0.15, (h_conf + n_conf) / 2.0 * 0.85)
    note = f"{h_note} | {n_note}"
    return "related", conf, note


def classify_stance(
    claim_text: str,
    evidence: Article,
    *,
    allow_llm: bool = False,
) -> tuple[str, float, str, str]:
    if allow_llm:
        llm = stance_llm(claim_text, evidence)
        if llm:
            stance, conf, note = llm
            return stance, conf, note, "llm"

    h_stance, h_conf, h_note = stance_heuristic(claim_text, evidence)
    nli = stance_nli(claim_text, evidence)
    if not nli:
        return h_stance, h_conf, h_note, "heuristic"

    n_stance, n_conf, n_note = nli
    stance, conf, note = _merge_heuristic_nli(
        h_stance, h_conf, h_note, n_stance, n_conf, n_note
    )
    return stance, conf, note, "heuristic+nli"
