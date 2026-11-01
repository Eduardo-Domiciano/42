#!/usr/bin/env python3
"""CLI: importa metadados leis-main (CF + federal) no SQLite do 42.

Uso (na pasta backend, com venv):
  python -m scripts.import_leis
  python -m scripts.import_leis --leis-root /caminho/leis-main --limit 500

Docker:
  docker compose exec api python -m scripts.import_leis
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Garante import de `app` quando rodado como script
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.db_migrate import ensure_sqlite_columns  # noqa: E402
from app.services.norma_import import import_leis, resolve_leis_root  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa normas (fase 1) no SQLite")
    parser.add_argument(
        "--leis-root",
        default=None,
        help="Raiz do clone leis-main (default: LEIS_ROOT ou ../leis-main)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita quantidade de arquivos (teste)",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns(engine)

    root = resolve_leis_root(args.leis_root)
    print(f"LEIS_ROOT={root}")
    db = SessionLocal()
    try:
        stats = import_leis(db, leis_root=root, limit=args.limit)
    finally:
        db.close()
    print(
        "ok scanned={scanned} upserted={upserted} "
        "skipped={skipped} errors={errors}".format(**stats)
    )
    return 0 if stats["errors"] == 0 or stats["upserted"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
