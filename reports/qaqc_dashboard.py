"""
reports/qaqc_dashboard.py  —  Phase 6
------------------------------------------
Project-wide QA/QC health summary — distinct from compliance/engine.py's
per-rule PASS/FAIL/WARNING/NOT_EVALUATED checks (spec Section A: the two
engines are architecturally separate). This module answers "is this
project's data trustworthy and complete enough to issue?", covering
things no single code rule checks:

  - calculation status mix (any FAIL? any still CALCULATED_NOT_APPROVED?)
  - compliance rule status mix
  - design-basis items still PENDING approval (spec Section 8/31 — nothing
    should be used in a final calc until APPROVED)
  - assumptions still PENDING_ENGINEER_APPROVAL (spec Section 31)
  - calculations that used FLAGGED-confidence or cross-code-fallback data
    (an audit trail of exactly which results are riding on a documented
    gap, not just a generic "some data is uncertain" note)
  - coverage gaps (MISSING_DATA calcs, NOT_EVALUATED compliance rules)

Writes one row per check to `qaqc_results` (schema.sql, previously
unused). Unlike `compliance_checks` (an accumulating audit log — each
run adds new rows, per compliance/engine.py's existing behavior), this
dashboard is a SNAPSHOT: rerunning it clears this project's previous
qaqc_results first, since re-running the dashboard should show the
project's *current* state, not accumulate one stale row per past click.
"""

from __future__ import annotations

import json


def _clear_previous(conn, project_id: int) -> None:
    conn.execute("DELETE FROM qaqc_results WHERE project_id = ?", (project_id,))


def _insert(conn, project_id: int, check_name: str, category: str, status: str, details: str) -> dict:
    conn.execute(
        """INSERT INTO qaqc_results (project_id, check_name, category, status, details)
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, check_name, category, status, details),
    )
    return {"check_name": check_name, "category": category, "status": status, "details": details}


def _current(conn, project_id, table):
    from compliance.governance import calculation_is_current
    rows = conn.execute(f'SELECT * FROM {table} WHERE project_id=?', (project_id,)).fetchall()
    return [r for r in rows if calculation_is_current(conn, project_id, r)], len(rows)


def _check_calculations(conn, project_id: int) -> dict:
    rows, total_history = _current(conn, project_id, 'calculations')
    counts = {status: sum(r['status'] == status for r in rows) for status in sorted({r['status'] for r in rows})}
    status = ('FAIL' if counts.get('FAIL') else 'MISSING_DATA' if not rows else
              'WARNING' if any(r['status'] != 'PASS' or r['review_status'] != 'VERIFIED' for r in rows) else 'PASS')
    return _insert(conn, project_id, 'Calculation status summary', 'calculations', status,
        f'{len(rows)} current calculation(s): {counts}; {total_history-len(rows)} historical/stale record(s) excluded. Technical calculation is not engineering approval.')


def _check_compliance(conn, project_id: int) -> dict:
    rows, total_history = _current(conn, project_id, 'compliance_checks')
    counts = {status: sum(r['status'] == status for r in rows) for status in sorted({r['status'] for r in rows})}
    status = ('FAIL' if counts.get('FAIL') else 'MISSING_DATA' if not rows else
              'WARNING' if any(r['status'] != 'PASS' for r in rows) else 'PASS')
    return _insert(conn, project_id, 'Compliance rule status summary', 'compliance', status,
        f'{len(rows)} current rule check(s): {counts}; {total_history-len(rows)} historical/stale checks excluded.')


def _check_design_basis(conn, project_id: int) -> dict:
    rows = conn.execute(
        "SELECT item_key, status FROM design_basis_items WHERE project_id=? ORDER BY item_key",
        (project_id,),
    ).fetchall()
    pending = [r["item_key"] for r in rows if r["status"] != "APPROVED"]
    total = len(rows)
    if not rows:
        status, details = "MISSING_DATA", "No design-basis entries recorded yet."
    elif pending:
        status = "WARNING"
        details = f"{len(pending)} of {total} design-basis item(s) not approved (pending or rejected): {', '.join(pending)}"
    else:
        status, details = "PASS", f"All {total} design-basis item(s) are APPROVED."
    return _insert(conn, project_id, "Design-basis approval status", "design_basis", status, details)


def _check_assumptions(conn, project_id: int) -> dict:
    rows = conn.execute(
        "SELECT assumption_id, status FROM assumptions WHERE project_id=? ORDER BY assumption_id",
        (project_id,),
    ).fetchall()
    pending = [r["assumption_id"] for r in rows if r["status"] not in ("APPROVED", "REJECTED")]
    total = len(rows)
    if not rows:
        status, details = "PASS", "No open assumptions recorded for this project."
    elif pending:
        status = "WARNING"
        details = f"{len(pending)} of {total} assumption(s) still PENDING_ENGINEER_APPROVAL: {', '.join(pending)}"
    else:
        status, details = "PASS", f"All {total} assumption(s) are resolved (APPROVED/EDITED/REJECTED)."
    return _insert(conn, project_id, "Assumption approval status", "assumptions", status, details)


def _check_flagged_data_in_use(conn, project_id: int) -> dict:
    """
    Audit trail: which SAVED calculation results rest on a FLAGGED-confidence
    table row or an explicit cross-code fallback? Matched on the same
    markers the calc modules themselves write into `reference`/`notes`
    when this happens (design_table_api.py's fallback policy; drainage.py/
    stormwater.py's confidence-downgrade notes) — not re-derived here.
    """
    current, _ = _current(conn, project_id, 'calculations')
    rows = [r for r in current if r['status'] in ('WARNING', 'ASSUMED') or
            any(word in ((r['reference'] or '') + ' ' + (r['notes'] or '')).lower() for word in ('flagged', 'fallback'))]
    if not rows:
        status, details = "PASS", "No saved calculation currently relies on FLAGGED data or a cross-code fallback."
    else:
        ids = [f"{r['calc_id']} ({r['calc_type']})" for r in rows]
        status = "WARNING"
        details = f"{len(rows)} calculation(s) rest on FLAGGED/fallback data — confirm before sign-off: " + \
                  "; ".join(ids)
    return _insert(conn, project_id, "Flagged / fallback data in use", "data_confidence", status, details)


def _check_coverage_gaps(conn, project_id: int) -> dict:
    current, _ = _current(conn, project_id, 'calculations')
    checks, _ = _current(conn, project_id, 'compliance_checks')
    n_missing = sum(r['status'] == 'MISSING_DATA' for r in current)
    n_ne = sum(r['status'] == 'NOT_EVALUATED' for r in checks)
    partial = sum(json.loads(r['intermediate_json'] or '{}').get('coverage_status') in ('PARTIAL', 'NOT_EVALUATED') for r in current)
    n_ne += partial
    if n_missing == 0 and n_ne == 0:
        status, details = "PASS", "No MISSING_DATA calculations and no NOT_EVALUATED compliance rules."
    else:
        status = "WARNING"
        details = (f"{n_missing} calculation(s) stopped on MISSING_DATA; "
                   f"{n_ne} compliance rule(s) NOT_EVALUATED (including partial model/drawing coverage — "
                   f"see docs/ARCHITECTURE.md Section D).")
    return _insert(conn, project_id, "Coverage gaps (missing data / not evaluated)", "coverage", status, details)


def run_qaqc(conn, project_id: int) -> list[dict]:
    """Runs every QA/QC check, clears and rewrites this project's qaqc_results, returns the summary rows."""
    with conn:
        _clear_previous(conn, project_id)
        results = [
            _check_calculations(conn, project_id),
            _check_compliance(conn, project_id),
            _check_design_basis(conn, project_id),
            _check_assumptions(conn, project_id),
            _check_flagged_data_in_use(conn, project_id),
            _check_coverage_gaps(conn, project_id),
        ]
        from compliance.governance import context
        governance = context(conn, project_id)
        results.append(_insert(conn, project_id, 'Code profile and adoption review', 'governance',
                               'WARNING' if governance['issues'] else 'PASS',
                               '; '.join(governance['issues']) or 'Verified code context'))

    return results


if __name__ == "__main__":
    from database.db import get_connection
    conn = get_connection()
    pid_row = conn.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
    if pid_row is None:
        print("No project found — run tests/demo_project.py first.")
    else:
        for r in run_qaqc(conn, pid_row["project_id"]):
            print(f"  [{r['status']:12s}] {r['check_name']:40s} {r['details']}")
    conn.close()
