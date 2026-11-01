"""Migrações leves para SQLite (ADD COLUMN / FTS / create_all cobre tabelas novas)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


SOURCE_COLUMNS: dict[str, str] = {
    "ownership_name": "VARCHAR(255)",
    "bias_score": "FLOAT",
    "bias_label": "VARCHAR(40)",
    "bias_note": "TEXT",
    "bias_catalog_version": "VARCHAR(20)",
    "source_role": "VARCHAR(80)",
    "topics": "VARCHAR(255)",
    "host_patterns": "TEXT",
}


def ensure_sqlite_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "sources" in tables:
            existing = {col["name"] for col in inspector.get_columns("sources")}
            for name, sql_type in SOURCE_COLUMNS.items():
                if name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE sources ADD COLUMN {name} {sql_type}")
                    )

        # Assessments duplicados (mesmo artigo + mesmo claim) → um só + índice único
        if "claim_assessments" in tables:
            conn.execute(
                text(
                    """
                    DELETE FROM claim_assessments
                    WHERE id NOT IN (
                        SELECT MIN(id) FROM claim_assessments
                        GROUP BY article_id, claim_id
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_claim_assessment_article_claim "
                    "ON claim_assessments (article_id, claim_id)"
                )
            )

        _ensure_norma_fts(conn, tables)


def _ensure_norma_fts(conn, tables: set[str]) -> None:
    """FTS5 sobre titulo/ementa das normas (content sync via triggers)."""
    if "normas" not in tables and "normas" not in {
        r[0]
        for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
    }:
        # create_all pode ter acabado de criar; reconsulta
        pass

    names = {
        r[0]
        for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        )
    }
    if "normas" not in names:
        return
    if "norma_fts" not in names:
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE norma_fts USING fts5(
                    titulo,
                    ementa,
                    urn UNINDEXED,
                    content='normas',
                    content_rowid='id'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO norma_fts(rowid, titulo, ementa, urn)
                SELECT id, COALESCE(titulo,''), COALESCE(ementa,''), urn FROM normas
                """
            )
        )

    # Triggers de sync (IF NOT EXISTS não existe para triggers — drop/create)
    for trig in (
        "normas_ai",
        "normas_ad",
        "normas_au",
    ):
        conn.execute(text(f"DROP TRIGGER IF EXISTS {trig}"))

    conn.execute(
        text(
            """
            CREATE TRIGGER normas_ai AFTER INSERT ON normas BEGIN
              INSERT INTO norma_fts(rowid, titulo, ementa, urn)
              VALUES (
                new.id,
                COALESCE(new.titulo, ''),
                COALESCE(new.ementa, ''),
                new.urn
              );
            END
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER normas_ad AFTER DELETE ON normas BEGIN
              INSERT INTO norma_fts(norma_fts, rowid, titulo, ementa, urn)
              VALUES (
                'delete',
                old.id,
                COALESCE(old.titulo, ''),
                COALESCE(old.ementa, ''),
                old.urn
              );
            END
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER normas_au AFTER UPDATE ON normas BEGIN
              INSERT INTO norma_fts(norma_fts, rowid, titulo, ementa, urn)
              VALUES (
                'delete',
                old.id,
                COALESCE(old.titulo, ''),
                COALESCE(old.ementa, ''),
                old.urn
              );
              INSERT INTO norma_fts(rowid, titulo, ementa, urn)
              VALUES (
                new.id,
                COALESCE(new.titulo, ''),
                COALESCE(new.ementa, ''),
                new.urn
              );
            END
            """
        )
    )
