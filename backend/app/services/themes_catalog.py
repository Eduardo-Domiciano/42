"""Catálogo de temas oficiais selecionáveis na análise (expansível)."""

from __future__ import annotations

# Começamos com economia; novos temas entram aqui + UI.
AVAILABLE_THEMES: list[dict[str, str]] = [
    {
        "slug": "economia",
        "label": "Economia",
        "description": (
            "Confronta números do texto com séries oficiais do Banco Central "
            "(Selic, IPCA, dólar) e prioriza fontes oficiais do tema."
        ),
    },
]

_KNOWN = {t["slug"] for t in AVAILABLE_THEMES}


def list_themes() -> list[dict[str, str]]:
    return list(AVAILABLE_THEMES)


def normalize_themes(themes: list[str] | None) -> list[str]:
    """Mantém só slugs conhecidos, sem duplicar, na ordem do catálogo."""
    if not themes:
        return []
    wanted = {str(t).strip().lower() for t in themes if str(t).strip()}
    return [t["slug"] for t in AVAILABLE_THEMES if t["slug"] in wanted]


def has_theme(themes: list[str] | None, slug: str) -> bool:
    return slug in normalize_themes(themes)
