from __future__ import annotations

import logging

from app.config import settings
from app.services.nn_embeddings import semantic_similarity
from app.services.nn_runtime import get_embedder, nn_enabled

logger = logging.getLogger(__name__)


def clickbait_score(title: str, body: str) -> float | None:
    """
    Complemento: score 0–1 (alto = mais clickbait).
    Usa divergência semântica título × início do corpo (embeddings).
    Retorna None se NN indisponível.
    """
    if not nn_enabled() or not settings.nn_clickbait_enabled:
        return None
    if not get_embedder():
        return None
    title = (title or "").strip()
    body = (body or "").strip()
    if len(title) < 8 or len(body) < 40:
        return None
    try:
        sim = semantic_similarity(title, body[:900])
        if sim is None:
            return None
        # Baixa similaridade título/corpo → maior risco de clickbait
        score = max(0.0, min(1.0, 1.0 - sim))
        return score
    except Exception as exc:
        logger.warning("Falha clickbait NN: %s", exc)
        return None


def blend_distortion(heuristic_distortion: float, title: str, body: str) -> tuple[float, str | None]:
    """Mistura distortion heurística com score NN (complemento)."""
    nn = clickbait_score(title, body)
    if nn is None:
        return heuristic_distortion, None
    # 60% heurística + 40% NN
    blended = max(0.0, min(1.0, 0.6 * heuristic_distortion + 0.4 * nn))
    note = f"Clickbait NN={nn:.2f} fundido à Distortion heurística={heuristic_distortion:.2f} → {blended:.2f}"
    return blended, note
