"""Idempotent, additive migration; never resets projects or source data."""
import json
from pathlib import Path


def ensure_governance_schema(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'projects' not in tables:
        raise ValueError('Initialize the engine schema before applying governance migration')
    changes = {
        'pipes': {'revit_model_key':'TEXT'},
        'tanks': {'revit_model_key':'TEXT'},
        'pumps': {'revit_model_key':'TEXT'},
        'revit_elements': {'revit_model_key':'TEXT'},
        'calculations': {'notes': 'TEXT', 'governance_json': 'TEXT',
                         'review_status': "TEXT NOT NULL DEFAULT 'LEGACY_UNVERIFIED'",
                         'is_current': 'INTEGER NOT NULL DEFAULT 0'},
        'compliance_checks': {'technical_status': 'TEXT', 'governance_json': 'TEXT',
                              'is_current': 'INTEGER NOT NULL DEFAULT 0'},
    }
    for table, columns in changes.items():
        existing = {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
        for name, declaration in columns.items():
            if name not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')
    statements = [
        '''CREATE TABLE IF NOT EXISTS project_calculation_packages (
            project_id INTEGER NOT NULL REFERENCES projects(project_id),
            package_sha256 TEXT NOT NULL, title TEXT NOT NULL, package_json TEXT NOT NULL,
            PRIMARY KEY(project_id,package_sha256))''',
        '''CREATE TABLE IF NOT EXISTS project_code_basis (
            project_id INTEGER PRIMARY KEY REFERENCES projects(project_id),
            profile_id TEXT NOT NULL, revision INTEGER NOT NULL,
            criteria_json TEXT NOT NULL, basis_status TEXT NOT NULL,
            reviewer TEXT, adoption_evidence TEXT, approved_context TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS governance_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(project_id),
            event_type TEXT NOT NULL, actor TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS rule_reviews (
            profile_id TEXT NOT NULL, rule_id TEXT NOT NULL REFERENCES code_rules(rule_id),
            status TEXT NOT NULL DEFAULT 'PENDING', applicability TEXT NOT NULL DEFAULT '',
            inputs TEXT NOT NULL DEFAULT '', units TEXT NOT NULL DEFAULT '', exceptions TEXT NOT NULL DEFAULT '',
            reviewer TEXT, source_evidence TEXT, benchmark_id TEXT,
            source_fingerprint TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(profile_id,rule_id))''',
        '''CREATE TABLE IF NOT EXISTS verification_benchmarks (
            benchmark_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, domain TEXT NOT NULL,
            purpose TEXT NOT NULL, expected_json TEXT, actual_json TEXT, tolerance REAL,
            reviewer TEXT, source_evidence TEXT, status TEXT NOT NULL DEFAULT 'PENDING',
            source_fingerprint TEXT, case_json TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''',
    ]
    for sql in statements:
        conn.execute(sql)
    conn.commit()


if __name__ == '__main__':
    import argparse
    from database.db import get_connection
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-path', type=Path)
    args = parser.parse_args()
    conn = get_connection(args.db_path)
    try:
        ensure_governance_schema(conn)
        print('Governance migration applied; existing records retained.')
    finally:
        conn.close()
