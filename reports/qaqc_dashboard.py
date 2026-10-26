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


def _check_calculations(conn, project_id: int) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM calculations WHERE project_id=? GROUP BY status",
        (project_id,),
    ).fetchall()
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    if counts.get("FAIL", 0) > 0:
        status = "FAIL"
    elif counts.get("MISSING_DATA", 0) > 0 or counts.get("WARNING", 0) > 0 or counts.get("ASSUMED", 0) > 0:
        status = "WARNING"
    elif total == 0:
        status = "MISSING_DATA"
    else:
        status = "PASS"
    details = f"{total} calculation(s): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) \
        if total else "No calculations recorded yet for this project."
    return _insert(conn, project_id, "Calculation status summary", "calculations", status, details)


def _check_compliance(conn, project_id: int) -> dict:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM compliance_checks WHERE project_id=? GROUP BY status",
        (project_id,),
    ).fetchall()
    counts = {r["status"]: r["n"] for r in rows}
    total = sum(counts.values())
    if counts.get("FAIL", 0) > 0:
        status = "FAIL"
    elif counts.get("WARNING", 0) > 0 or counts.get("NOT_EVALUATED", 0) > 0:
        status = "WARNING"
    elif total == 0:
        status = "MISSING_DATA"
    else:
        status = "PASS"
    details = f"{total} rule check(s): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) \
        if total else "Compliance check has not been run yet for this project (Code Compliance / QA-QC page)."
    return _insert(conn, project_id, "Compliance rule status summary", "compliance", status, details)


def _check_design_basis(conn, project_id: int) -> dict:
    rows = conn.execute(
        "SELECT item_key, status FROM design_basis_items WHERE project_id=? ORDER BY item_key",
        (project_id,),
    ).fetchall()
    pending = [r["item_key"] for r in rows if r["status"] == "PENDING"]
    total = len(rows)
    if not rows:
        status, details = "MISSING_DATA", "No design-basis entries recorded yet."
    elif pending:
        status = "WARNING"
        details = f"{len(pending)} of {total} design-basis item(s) still PENDING approval: {', '.join(pending)}"
    else:
        status, details = "PASS", f"All {total} design-basis item(s) are APPROVED or REJECTED — none PENDING."
    return _insert(conn, project_id, "Design-basis approval status", "design_basis", status, details)


def _check_assumptions(conn, project_id: int) -> dict:
    rows = conn.execute(
        "SELECT assumption_id, status FROM assumptions WHERE project_id=? ORDER BY assumption_id",
        (project_id,),
    ).fetchall()
    pending = [r["assumption_id"] for r in rows if r["status"] == "PENDING_ENGINEER_APPROVAL"]
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
    rows = conn.execute(
        """SELECT calc_id, calc_type, reference, status FROM calculations
           WHERE project_id=? AND (
               reference LIKE '%fallback from%' OR status IN ('WARNING', 'ASSUMED')
           ) ORDER BY calc_id""",
        (project_id,),
    ).fetchall()
    if not rows:
        status, details = "PASS", "No saved calculation currently relies on FLAGGED data or a cross-code fallback."
    else:
        ids = [f"{r['calc_id']} ({r['calc_type']})" for r in rows]
        status = "WARNING"
        details = f"{len(rows)} calculation(s) rest on FLAGGED/fallback data — confirm before sign-off: " + \
                  "; ".join(ids)
    return _insert(conn, project_id, "Flagged / fallback data in use", "data_confidence", status, details)


def _check_coverage_gaps(conn, project_id: int) -> dict:
    missing_calcs = conn.execute(
        "SELECT calc_id, calc_type FROM calculations WHERE project_id=? AND status='MISSING_DATA'",
        (project_id,),
    ).fetchall()
    not_evaluated = conn.execute(
        "SELECT rule_id FROM compliance_checks WHERE project_id=? AND status='NOT_EVALUATED'",
        (project_id,),
    ).fetchall()
    n_missing, n_ne = len(missing_calcs), len(not_evaluated)
    if n_missing == 0 and n_ne == 0:
        status, details = "PASS", "No MISSING_DATA calculations and no NOT_EVALUATED compliance rules."
    else:
        status = "WARNING"
        details = (f"{n_missing} calculation(s) stopped on MISSING_DATA; "
                   f"{n_ne} compliance rule(s) NOT_EVALUATED (mostly BIM-topology rules pending Phase 7 — "
                   f"see docs/ARCHITECTURE.md Section D).")
    return _insert(conn, project_id, "Coverage gaps (missing data / not evaluated)", "coverage", status, details)


def run_qaqc(conn, project_id: int) -> list[dict]:
    """Runs every QA/QC check, clears and rewrites this project's qaqc_results, returns the summary rows."""
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
    conn.commit()
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
