"""Print a source/data inventory without touching the application database.

Run from the repository root: python -m tools.baseline_inventory
Workbook contents are not included in the output.
"""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from database.db import init_db
from database.load_design_tables import DATA_DIR, FILE_TO_CODE, load_all_workbooks
from database.load_confirmed_additions import load_all_confirmed_additions


def inventory():
    root = Path(__file__).resolve().parents[1]
    result = {"python": platform.python_version(), "platform": platform.system(),
              "packages": {}, "workbooks": [], "codes": []}
    for package in ("pytest", "openpyxl", "streamlit", "pandas"):
        try:
            result["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][package] = None
    for name, code in FILE_TO_CODE.items():
        path = DATA_DIR / name
        result["workbooks"].append({"file": path.relative_to(root).as_posix(), "code": code,
                                    "available": path.exists(),
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None})
    conn = init_db(":memory:")
    try:
        load_all_rules(conn)
        sync_predicate_flags(conn)
        result["workbook_load"] = load_all_workbooks(conn)
        # Keep only counts / availability; no table caveats or numeric source data.
        result["workbook_load"] = {
            code: {k: v for k, v in summary.items() if k in ("tables_loaded", "rows_loaded", "flagged_rows", "error")}
            for code, summary in result["workbook_load"].items()}
        load_all_confirmed_additions(conn)
        for row in conn.execute("SELECT code_id,COUNT(*) AS rules,SUM(has_predicate) AS executable "
                                 "FROM code_rules GROUP BY code_id ORDER BY code_id"):
            result["codes"].append(dict(row))
        result["tables"] = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    finally:
        conn.close()
    return result


if __name__ == "__main__":
    print(json.dumps(inventory(), indent=2))
