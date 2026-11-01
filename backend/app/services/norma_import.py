"""ETL: frontmatter do leis-main → tabela normas (+ FTS via triggers)."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.models import Norma

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_CONSTITUICAO_URN = "urn:lex:br:federal:constituicao:1988-10-05"


def resolve_leis_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if settings.leis_root:
        return Path(settings.leis_root).expanduser().resolve()
    # backend/ → 42/ → Code/42/leis-main  ou  backend/../leis-main
    candidates = [
        ROOT.parent.parent / "leis-main",  # .../Code/42/leis-main
        ROOT.parent / "leis-main",
        ROOT / "leis-main",
    ]
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    return candidates[0]


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _read_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _should_skip(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    for part in rel.parts:
        if part.startswith("_"):
            return True
    return False


def _esfera_from_path(rel: Path) -> tuple[str, str | None, str | None, str | None]:
    """Retorna (esfera, uf, municipio, orgao) a partir do path relativo."""
    parts = rel.parts
    if not parts:
        return "federal", None, None, None
    top = parts[0]
    if top == "federal" or rel.name == "constituicao.md":
        return "federal", None, None, None
    if top == "estaduais" and len(parts) >= 2:
        return "estadual", parts[1].upper()[:2], None, None
    if top == "municipais" and len(parts) >= 3:
        return "municipal", parts[1].upper()[:2], parts[2], None
    if top == "reguladores":
        orgao = parts[1] if len(parts) > 1 else None
        return "regulador", None, None, orgao
    return top[:40], None, None, None


def _constituicao_meta(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = "Constituição da República Federativa do Brasil de 1988"
    for line in text.splitlines()[:5]:
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break
    ementa = (
        "Constituição Federal de 1988 — texto compilado vigente "
        "(metadados sintéticos; corpo em path_md)."
    )
    return {
        "urn": _CONSTITUICAO_URN,
        "titulo": title,
        "ementa": ementa,
        "tipo": "Constituição",
        "numero": None,
        "data": date(1988, 10, 5),
        "revogada": False,
        "versao_texto": "compilada",
        "fonte": (
            "https://www.planalto.gov.br/ccivil_03/constituicao/"
            "constituicaocompilado.htm"
        ),
        "baixado_em": None,
    }


def iter_fase1_paths(root: Path) -> list[Path]:
    """constituicao.md + federal/**/*.md (sem pastas _*)."""
    out: list[Path] = []
    constituicao = root / "constituicao.md"
    if constituicao.is_file():
        out.append(constituicao)
    federal = root / "federal"
    if federal.is_dir():
        for path in federal.rglob("*.md"):
            if _should_skip(path, root):
                continue
            out.append(path)
    return out


def upsert_norma_from_meta(
    db: Session,
    *,
    root: Path,
    path: Path,
    meta: dict,
) -> Norma | None:
    urn = str(meta.get("urn") or "").strip()
    if not urn:
        return None

    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)

    esfera, uf, municipio, orgao = _esfera_from_path(rel)
    # path relativo como string posix
    path_md = rel.as_posix()

    row = db.scalar(select(Norma).where(Norma.urn == urn))
    if not row:
        row = Norma(urn=urn)
        db.add(row)

    row.esfera = esfera
    row.uf = uf
    row.municipio = municipio
    row.orgao = orgao
    row.tipo = str(meta.get("tipo") or "")[:80]
    numero = meta.get("numero")
    row.numero = str(numero)[:40] if numero is not None else None
    row.data_norma = _parse_date(meta.get("data") or meta.get("data_norma"))
    row.titulo = (meta.get("titulo") or None) and str(meta["titulo"])
    row.ementa = (meta.get("ementa") or None) and str(meta["ementa"])
    row.revogada = bool(meta.get("revogada") or False)
    vt = meta.get("versao_texto")
    row.versao_texto = str(vt)[:40] if vt else None
    fonte = meta.get("fonte") or meta.get("fonte_url")
    row.fonte_url = str(fonte) if fonte else None
    row.path_md = path_md
    row.baixado_em = _parse_date(meta.get("baixado_em"))
    return row


def import_leis(
    db: Session,
    *,
    leis_root: str | Path | None = None,
    limit: int | None = None,
    commit_every: int = 200,
) -> dict[str, int]:
    """
    Importa fase 1 (CF + federal). Upsert por urn.
    Retorna contadores: scanned, upserted, skipped, errors.
    """
    root = resolve_leis_root(leis_root)
    if not root.is_dir():
        raise FileNotFoundError(f"LEIS_ROOT não encontrado: {root}")

    paths = iter_fase1_paths(root)
    if limit is not None:
        paths = paths[:limit]

    stats = {"scanned": 0, "upserted": 0, "skipped": 0, "errors": 0}
    for i, path in enumerate(paths, start=1):
        stats["scanned"] += 1
        try:
            if path.name == "constituicao.md" and path.parent == root:
                meta = _constituicao_meta(path, root)
            else:
                meta = _read_frontmatter(path)
                if not meta or not meta.get("urn"):
                    stats["skipped"] += 1
                    continue
            row = upsert_norma_from_meta(db, root=root, path=path, meta=meta)
            if row is None:
                stats["skipped"] += 1
                continue
            stats["upserted"] += 1
        except Exception:
            stats["errors"] += 1
            continue

        if i % commit_every == 0:
            db.commit()

    db.commit()
    return stats
