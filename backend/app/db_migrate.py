"""Migrações leves para SQLite (ADD COLUMN / create_all cobre tabelas novas)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


SOURCE_COLUMNS: dict[str, str] = {
    "ownership_name": "VARCHAR(255)",
    "bias_score": "FLOAT",
    "bias_label": "VARCHAR(40)",
    "bias_note": "TEXT",
    "bias_catalog_version": "VARCHAR(20)",
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
