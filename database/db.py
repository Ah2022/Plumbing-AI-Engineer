"""
database/db.py
---------------
Thin SQLite connection helper for the Plumbing Design Engine.

Kept deliberately small: the schema lives in schema.sql (plain SQL,
portable to PostgreSQL later), this module just wires it up.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).parent / "plumbing_engine.db"


def get_db_path(db_path: Path | str | None = None) -> Path:
    """Resolve an explicit path or a per-process test/deployment override."""
    return Path(db_path if db_path is not None else os.environ.get(
        "PLUMBING_ENGINE_DB_PATH", str(DEFAULT_DB_PATH))).expanduser()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enforced and Row access."""
    conn = sqlite3.connect(str(get_db_path(db_path)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str | None = None, reset: bool = False) -> sqlite3.Connection:
    """
    Create the database from schema.sql.

    reset=True drops and recreates the file — use only for dev/test.
    """
    db_path = get_db_path(db_path)
    if reset and db_path.exists():
        db_path.unlink()

    conn = get_connection(db_path)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    return conn


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize the engine database without replacing existing data.")
    parser.add_argument("--db-path", type=Path, help="Database file (or PLUMBING_ENGINE_DB_PATH).")
    parser.add_argument("--reset", action="store_true", help="Explicitly delete and recreate this database.")
    args = parser.parse_args()
    db_path = get_db_path(args.db_path)
    if db_path.exists() and not args.reset:
        print(f"Existing database retained at {db_path}. Use --reset only for disposable data.")
        raise SystemExit(0)
    conn = init_db(db_path, reset=args.reset)
    print(f"Initialized database at {db_path}")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    print(f"{len(tables)} tables created:")
    for t in tables:
        print(" -", t["name"])
    conn.close()
