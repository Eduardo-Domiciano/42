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
