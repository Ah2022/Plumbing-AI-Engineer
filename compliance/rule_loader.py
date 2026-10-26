"""
compliance/rule_loader.py
--------------------------
Loads the supplied machine-readable code-rule dataset
(database/codes/<CODE>/<domain>_rules.json) into the `codes` and
`code_rules` SQLite tables.

This module is fully functional today because the input data (32 rules
across IPC, UPC, EGYPT_LOCAL, SAUDI_SBC_701) already exists and was
supplied by the engineer. It does NOT invent, infer, or supplement any
rule content — it is a straight, auditable ETL from JSON to SQLite.

IMPORTANT — scope of this dataset:
This dataset is a *qualitative compliance-checklist* (condition / action /
severity / reference), not a numeric design-table database. Only one rule
(IPC-W-002) carries a hard numeric parameter. Fixture-unit tables, DFU
tables, velocity limits, minimum slopes, vent length/diameter tables, and
rainfall-intensity tables are NOT present in this dataset and must be
supplied separately into `design_tables` / `design_table_values` — see
docs/ARCHITECTURE.md, section H.
"""

from __future__ import annotations

import json
from pathlib import Path

from database.db import get_connection, init_db

CODES_DIR = Path(__file__).parent.parent / "database" / "codes"

# Human-readable code metadata (jurisdiction) — NOT engineering values,
# just labeling, safe to state here.
CODE_METADATA = {
    "IPC": {"jurisdiction": "US model code (adopted in many jurisdictions incl. parts of the Gulf)"},
    "UPC": {"jurisdiction": "US model code (adopted in many jurisdictions incl. parts of the Gulf)"},
    "EGYPT_LOCAL": {"jurisdiction": "Egypt"},
    "SAUDI_SBC_701": {"jurisdiction": "Saudi Arabia"},
}

DOMAIN_FILES = ["water_rules.json", "drainage_rules.json", "vent_rules.json", "storm_rules.json"]


def load_all_rules(conn) -> dict:
    """Load every code's README + rule files into the DB. Returns a summary dict."""
    summary = {}
    code_dirs = sorted(p for p in CODES_DIR.iterdir() if p.is_dir())

    for code_dir in code_dirs:
        code_id = code_dir.name
        readme_path = code_dir / "README.json"
        readme = json.loads(readme_path.read_text(encoding="utf-8")) if readme_path.exists() else {}
        code_name = readme.get("code_family", {}).get("code", code_id)
        schema_version = readme.get("schema_version")

        conn.execute(
            """INSERT OR REPLACE INTO codes (code_id, code_name, jurisdiction, schema_version, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (
                code_id,
                code_name,
                CODE_METADATA.get(code_id, {}).get("jurisdiction"),
                schema_version,
                readme.get("implementation_note"),
            ),
        )

        rule_count = 0
        for domain_file in DOMAIN_FILES:
            file_path = code_dir / domain_file
            if not file_path.exists():
                continue
            data = json.loads(file_path.read_text(encoding="utf-8"))
            for rule in data.get("rules", []):
                params = rule.get("parameters")
                conn.execute(
                    """INSERT OR REPLACE INTO code_rules
                       (rule_id, code_id, domain, severity, condition_text, action_text,
                        reference, source_note, parameters_json, has_predicate)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rule["rule_id"],
                        code_id,
                        rule["domain"],
                        rule["severity"],
                        rule["condition"],
                        rule["action"],
                        rule.get("reference"),
                        rule.get("source_note"),
                        json.dumps(params) if params else None,
                        0,  # has_predicate set later by rule_registry.sync_predicate_flags()
                    ),
                )
                rule_count += 1
        summary[code_id] = rule_count

    conn.commit()
    return summary


if __name__ == "__main__":
    conn = init_db(reset=True)
    result = load_all_rules(conn)
    total = sum(result.values())
    print("Loaded code rules:")
    for code_id, n in result.items():
        print(f"  {code_id:16s} {n:3d} rules")
    print(f"  {'TOTAL':16s} {total:3d} rules")

    # Sanity spot-check
    row = conn.execute(
        "SELECT * FROM code_rules WHERE rule_id = 'IPC-W-002'"
    ).fetchone()
    print("\nSpot check — IPC-W-002:")
    print(f"  severity   : {row['severity']}")
    print(f"  condition  : {row['condition_text']}")
    print(f"  parameters : {row['parameters_json']}")
    print(f"  reference  : {row['reference']}")
    conn.close()
