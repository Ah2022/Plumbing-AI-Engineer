"""Additive review history; never replaces project or calculation records."""


def ensure_review_schema(conn):
    for sql in [
        '''CREATE TABLE IF NOT EXISTS calculation_provenance (
            calc_id TEXT PRIMARY KEY REFERENCES calculations(calc_id) ON DELETE CASCADE,
            input_sha256 TEXT NOT NULL, engine_sha256 TEXT NOT NULL,
            manifest_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS calculation_overrides (
            override_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            calc_id TEXT NOT NULL REFERENCES calculations(calc_id), field TEXT NOT NULL,
            computed_json TEXT NOT NULL, proposed_value REAL NOT NULL, unit TEXT NOT NULL,
            actor TEXT NOT NULL, reason TEXT NOT NULL, input_sha256 TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS review_snapshots (
            snapshot_id TEXT PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(project_id),
            revision INTEGER NOT NULL, label TEXT NOT NULL, actor TEXT NOT NULL,
            packet_sha256 TEXT NOT NULL, packet_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(project_id, revision))''',
        '''CREATE TABLE IF NOT EXISTS revit_model_imports (
            project_id INTEGER NOT NULL REFERENCES projects(project_id), model_key TEXT NOT NULL,
            model_identity TEXT NOT NULL, model_name TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            payload_json TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(project_id,model_key))''',
        '''CREATE TABLE IF NOT EXISTS revit_element_identities (
            project_id INTEGER NOT NULL REFERENCES projects(project_id), model_key TEXT NOT NULL,
            element_id TEXT NOT NULL, unique_id TEXT, PRIMARY KEY(project_id,model_key,element_id))''',
    ]:
        conn.execute(sql)
    # Compatibility for databases initialized by the first review-schema build.
    # Provenance belongs to its calculation; attributed overrides still prevent
    # deleting their calculation through the existing foreign-key constraint.
    conn.execute('''CREATE TRIGGER IF NOT EXISTS delete_calculation_provenance
        BEFORE DELETE ON calculations BEGIN
        DELETE FROM calculation_provenance WHERE calc_id=OLD.calc_id;
        END''')
