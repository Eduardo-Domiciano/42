from __future__ import annotations

import logging

from app.models import Article
from app.services.nn_runtime import get_nli_bundle

logger = logging.getLogger(__name__)


def _map_label(raw: str) -> str:
    label = raw.lower()
    if "entail" in label or label in {"supported", "support", "yes"}:
        return "supports"
    if "contradict" in label or label in {"refutes", "refute", "no", "contradiction"}:
        return "refutes"
    if "neutral" in label:
        return "related"
    return "related"


def stance_nli(claim_text: str, evidence: Article) -> tuple[str, float, str] | None:
    """
    Complemento NLI: claim (hipótese) × trechos da evidência (premissa).
    Retorna (stance, confidence, note) ou None se modelo indisponível.
    """
    bundle = get_nli_bundle()
    if not bundle or not claim_text.strip():
        return None

    blob = f"{evidence.title or ''}\n{(evidence.body or '')[:3000]}".strip()
    if not blob:
        return None

    chunks = [c.strip() for c in blob.split("\n\n") if c.strip()]
    if not chunks:
        chunks = [blob[:800]]
    chunks = chunks[:8]
    if len(chunks) == 1 and len(chunks[0]) > 900:
        text = chunks[0]
        chunks = [text[i : i + 700] for i in range(0, min(len(text), 2800), 700)]

    try:
        import torch

        tokenizer = bundle["tokenizer"]
        model = bundle["model"]
        device = bundle["device"]
        id2label = bundle["id2label"]

        with torch.no_grad():
            inputs = tokenizer(
                chunks,
                [claim_text] * len(chunks),
                truncation=True,
                padding=True,
                max_length=512,
                return_tensors="pt",
            ).to(device)
            outputs = model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1).cpu()

        best_conf = -1.0
        best_stance = "related"
        best_idx = 0
        for i in range(probs.shape[0]):
            pred_i = int(torch.argmax(probs[i]).item())
            conf_i = float(probs[i][pred_i].item())
            stance_i = _map_label(id2label.get(pred_i, str(pred_i)))
            if conf_i > best_conf:
                best_conf = conf_i
                best_stance = stance_i
                best_idx = i

        # Se houver sinal forte de entail/contradict em algum chunk, prefira-o
        for i in range(probs.shape[0]):
            for idx, lab in id2label.items():
                p = float(probs[i][int(idx)].item())
                mapped = _map_label(str(lab))
                if mapped in {"supports", "refutes"} and p >= 0.45 and p >= best_conf - 0.05:
                    if p > best_conf or mapped != best_stance:
                        best_conf = p
                        best_stance = mapped
                        best_idx = i

        note = (
            f"NLI ({best_stance}, conf={best_conf:.2f}) no trecho: "
            f"{chunks[best_idx][:120]}…"
        )
        return best_stance, max(0.05, min(0.99, best_conf)), note
    except Exception as exc:
        logger.warning("Falha NLI: %s", exc)
        return None
