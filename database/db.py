"""
database/db.py
---------------
Thin SQLite connection helper for the Plumbing Design Engine.

Kept deliberately small: the schema lives in schema.sql (plain SQL,
portable to PostgreSQL later), this module just wires it up.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).parent / "plumbing_engine.db"


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enforced and Row access."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH, reset: bool = False) -> sqlite3.Connection:
    """
    Create the database from schema.sql.

    reset=True drops and recreates the file — use only for dev/test.
    """
    db_path = Path(db_path)
    if reset and db_path.exists():
        db_path.unlink()

    conn = get_connection(db_path)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    return conn


if __name__ == "__main__":
    conn = init_db(reset=True)
    print(f"Initialized database at {DEFAULT_DB_PATH}")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    print(f"{len(tables)} tables created:")
    for t in tables:
        print(" -", t["name"])
    conn.close()
