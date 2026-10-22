from __future__ import annotations

import logging

from app.models import Article
from app.services.nn_runtime import get_embedder

logger = logging.getLogger(__name__)


def _article_text(article: Article) -> str:
    title = article.title or ""
    body = (article.body or article.excerpt or "")[:1200]
    return f"{title}\n{body}".strip()


def semantic_similarity(a: str, b: str) -> float | None:
    embedder = get_embedder()
    if not embedder or not a.strip() or not b.strip():
        return None
    try:
        from sentence_transformers import util

        va, vb = embedder.encode([a, b], show_progress_bar=False, convert_to_tensor=True)
        score = float(util.cos_sim(va, vb).item())
        return max(0.0, min(1.0, score))
    except Exception as exc:
        logger.warning("Falha embeddings similarity: %s", exc)
        return None


def rank_articles_by_claim(
    claim_text: str,
    articles: list[Article],
    *,
    top_k: int,
) -> list[tuple[Article, float]]:
    """
    Complementa LIKE: reordena artigos candidatos por similaridade semântica ao claim.
    Se embeddings indisponíveis, devolve a lista original com score 0.
    """
    if not articles:
        return []
    embedder = get_embedder()
    if not embedder or not claim_text.strip():
        return [(a, 0.0) for a in articles[:top_k]]

    try:
        from sentence_transformers import util

        texts = [_article_text(a) or a.url for a in articles]
        claim_vec = embedder.encode(claim_text, show_progress_bar=False, convert_to_tensor=True)
        doc_vecs = embedder.encode(texts, show_progress_bar=False, convert_to_tensor=True)
        sims = util.cos_sim(claim_vec, doc_vecs)[0].cpu().tolist()
        ranked = sorted(
            zip(articles, sims, strict=True),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(a, float(s)) for a, s in ranked[:top_k]]
    except Exception as exc:
        logger.warning("Falha rank embeddings: %s", exc)
        return [(a, 0.0) for a in articles[:top_k]]
