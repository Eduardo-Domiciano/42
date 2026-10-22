"""Carregamento lazy das redes neurais. Se falhar, o pipeline segue sem NN."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_nli_bundle: dict[str, Any] | None = None
_embedder: Any = None
_nli_tried = False
_embed_tried = False
_packages_ok: bool | None = None


def nn_packages_installed() -> bool:
    global _packages_ok
    if _packages_ok is not None:
        return _packages_ok
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        import sentence_transformers  # noqa: F401

        _packages_ok = True
    except Exception:
        _packages_ok = False
    return _packages_ok


def nn_enabled() -> bool:
    return bool(settings.nn_enabled) and nn_packages_installed()


def nli_status() -> dict[str, Any]:
    return {
        "packages_installed": nn_packages_installed(),
        "nn_enabled": settings.nn_enabled,
        "nli_enabled": settings.nn_nli_enabled,
        "nli_loaded": _nli_bundle is not None,
        "embeddings_enabled": settings.nn_embeddings_enabled,
        "embeddings_loaded": _embedder is not None,
        "clickbait_enabled": settings.nn_clickbait_enabled,
        "nli_model": settings.nn_nli_model,
        "embed_model": settings.nn_embed_model,
    }


def get_nli_bundle() -> dict[str, Any] | None:
    """Retorna {tokenizer, model, device, id2label} ou None."""
    global _nli_bundle, _nli_tried
    if not nn_enabled() or not settings.nn_nli_enabled:
        return None
    if _nli_bundle is not None:
        return _nli_bundle
    if _nli_tried:
        return None
    with _lock:
        if _nli_bundle is not None:
            return _nli_bundle
        if _nli_tried:
            return None
        _nli_tried = True
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            name = settings.nn_nli_model
            logger.info("Carregando NLI %s em %s", name, device)
            tokenizer = AutoTokenizer.from_pretrained(name)
            model = AutoModelForSequenceClassification.from_pretrained(name)
            model.to(device)
            model.eval()
            id2label = {
                int(k): str(v).lower()
                for k, v in getattr(model.config, "id2label", {}).items()
            }
            _nli_bundle = {
                "tokenizer": tokenizer,
                "model": model,
                "device": device,
                "id2label": id2label,
            }
            return _nli_bundle
        except Exception as exc:
            logger.warning("NLI indisponível (fallback heurística): %s", exc)
            _nli_bundle = None
            return None


def get_embedder() -> Any | None:
    global _embedder, _embed_tried
    if not nn_enabled() or not settings.nn_embeddings_enabled:
        return None
    if _embedder is not None:
        return _embedder
    if _embed_tried:
        return None
    with _lock:
        if _embedder is not None:
            return _embedder
        if _embed_tried:
            return None
        _embed_tried = True
        try:
            from sentence_transformers import SentenceTransformer

            name = settings.nn_embed_model
            logger.info("Carregando embeddings %s", name)
            _embedder = SentenceTransformer(name)
            return _embedder
        except Exception as exc:
            logger.warning("Embeddings indisponíveis (fallback LIKE): %s", exc)
            _embedder = None
            return None
