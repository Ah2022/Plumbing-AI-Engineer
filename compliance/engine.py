"""
compliance/engine.py
----------------------
Runs every registered rule predicate (see rule_registry.py) against a
project's recorded data, and writes the results to `compliance_checks`.

Rules with no registered predicate are recorded as NOT_EVALUATED —
they are surfaced to the engineer as needing manual review or a future
BIM-topology check, never silently skipped and never silently passed.
"""

from __future__ import annotations

from database.db import get_connection
from compliance.rule_registry import RULE_PREDICATES, CheckResult


def run_compliance_for_project(conn, project_id: int, code_id: str) -> list[dict]:
    import json
    from compliance.governance import context
    governance = context(conn, project_id)
    project = conn.execute('SELECT code_id FROM projects WHERE project_id=?', (project_id,)).fetchone()
    if project['code_id'] != code_id:
        raise ValueError('Requested compliance code differs from the project code')
    rules = conn.execute(
        "SELECT * FROM code_rules WHERE code_id = ? ORDER BY rule_id", (code_id,)
    ).fetchall()

    results = []
    for rule in rules:
        predicate = RULE_PREDICATES.get(rule["rule_id"])
        if predicate is None:
            result = CheckResult(
                status="NOT_EVALUATED",
                reason="No executable predicate registered yet — requires BIM topology "
                       "data or engineer's manual review. See docs/ARCHITECTURE.md.",
            )
        else:
            result = predicate(conn, project_id, rule)

        technical_status = result.status
        if result.status == 'PASS' and governance['review_status'] != 'VERIFIED':
            result = CheckResult('NOT_EVALUATED', actual_value=result.actual_value,
                                 required_value=result.required_value,
                                 reason='Technical predicate returned PASS; code verification/adoption remains pending. ' +
                                 '; '.join(governance['issues']))
        conn.execute(
            """INSERT INTO compliance_checks
               (project_id, rule_id, target_type, target_id, actual_value,
                required_value, status, reason,technical_status,governance_json,is_current)
               VALUES (?, ?, 'project', ?, ?, ?, ?, ?,?,?,1)""",
            (
                project_id, rule["rule_id"], str(project_id),
                result.actual_value, result.required_value, result.status, result.reason,
                technical_status,json.dumps(governance,sort_keys=True),
            ),
        )
        results.append({
            "rule_id": rule["rule_id"],
            "severity": rule["severity"],
            "status": result.status,
            "technical_status": technical_status,
            "review_status": governance['review_status'],
            "reason": result.reason,
            "reference": rule["reference"],
        })
    conn.commit()
    return results


if __name__ == "__main__":
    conn = get_connection()
    pid_row = conn.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
    if pid_row is None:
        print("No project found — run tests/demo_project.py first.")
    else:
        results = run_compliance_for_project(conn, pid_row["project_id"], "IPC")
        for r in results:
            print(f"  {r['rule_id']:14s} [{r['severity']:7s}] {r['status']:14s} {r['reason'] or ''}")
    conn.close()
