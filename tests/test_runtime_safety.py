"""Verify that test/setup commands preserve an existing user database."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def sentinel(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sentinel (value TEXT)")
    conn.execute("INSERT INTO sentinel VALUES ('preserve me')")
    conn.commit()
    conn.close()


def assert_preserved(path):
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT value FROM sentinel").fetchone()[0] == "preserve me"
    finally:
        conn.close()


def test_database_cli_preserves_existing_file(tmp_path):
    path = tmp_path / "existing.db"
    sentinel(path)
    result = subprocess.run([sys.executable, "-m", "database.db", "--db-path", str(path)],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert_preserved(path)


def test_demo_preserves_configured_database(tmp_path):
    from database.load_design_tables import DATA_DIR, FILE_TO_CODE
    if not all((DATA_DIR / name).exists() for name in FILE_TO_CODE):
        pytest.skip("Full demo requires the locally supplied design workbooks")
    path = tmp_path / "existing.db"
    sentinel(path)
    env = dict(os.environ, PLUMBING_ENGINE_DB_PATH=str(path), PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, "-m", "tests.demo_project"], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert_preserved(path)
