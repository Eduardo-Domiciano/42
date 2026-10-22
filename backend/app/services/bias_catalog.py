from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import ROOT

CATALOG_PATH = ROOT / "catalog" / "bias_br.yml"


@lru_cache(maxsize=1)
def load_bias_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {"version": "0", "sources": {}, "defaults": {}}
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    data.setdefault("sources", {})
    data.setdefault("defaults", {})
    return data


def catalog_version() -> str:
    return str(load_bias_catalog().get("version") or "0")


def bias_for_slug(slug: str) -> dict[str, Any]:
    catalog = load_bias_catalog()
    entry = catalog.get("sources", {}).get(slug)
    if entry:
        return dict(entry)
    default = (catalog.get("defaults") or {}).get("unlisted") or {}
    return dict(default)


def ownership_display(slug: str, independence_group: str | None) -> str | None:
    entry = bias_for_slug(slug)
    if entry.get("ownership_name"):
        return str(entry["ownership_name"])
    aliases = load_bias_catalog().get("ownership_aliases") or {}
    if independence_group and independence_group in aliases:
        return str(aliases[independence_group])
    return independence_group


def bias_label_pt(label: str | None) -> str:
    mapping = {
        "institutional": "institucional",
        "left": "esquerda",
        "center_left": "centro-esquerda",
        "center": "centro",
        "center_right": "centro-direita",
        "right": "direita",
        "unknown": "desconhecida",
    }
    if not label:
        return "desconhecida"
    return mapping.get(label, label)
