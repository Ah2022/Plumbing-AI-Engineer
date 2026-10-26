"""
reports/report_generator.py  —  Phase 6
---------------------------------------------
The formatted calculation-sheet report (spec Section 23), built from
what actually exists in the database — never re-computes or re-derives
a number; only reads back what the calculation/compliance/QA-QC engines
already produced and saved. Two output forms:

  generate_calculation_report(conn, project_id)          -> structured dict
  generate_calculation_report_markdown(conn, project_id) -> Markdown text,
      built from that same dict, for the engineer to review, print to
      PDF, or paste into a formal deliverable.

CSV export of the underlying tables (calculations, compliance_checks,
design_basis_items, assumptions) stays in the Streamlit Report page as
before — this module is the human-readable narrative report that sits
alongside those raw exports.
"""

from __future__ import annotations

import datetime
import json
from compliance.governance import context


def _project_row(conn, project_id: int) -> dict:
    row = conn.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
    return dict(row) if row else {}


def _design_basis_rows(conn, project_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM design_basis_items WHERE project_id=? ORDER BY item_key", (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def _calculation_rows(conn, project_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM calculations WHERE project_id=? ORDER BY calc_id", (project_id,)
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["inputs"] = json.loads(d.get("inputs_json") or "{}")
        d["intermediate"] = json.loads(d.get("intermediate_json") or "{}")
        from compliance.governance import calculation_is_current
        d['current'] = calculation_is_current(conn, project_id, r)
        d['governance'] = json.loads(d.get('governance_json') or '{}')
        if not d['current']:
            d['review_status'] = 'STALE_RECALCULATION_REQUIRED'
        out.append(d)
    return out


def _compliance_rows(conn, project_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT cc.*, cr.severity, cr.condition_text FROM compliance_checks cc "
        "JOIN code_rules cr ON cr.rule_id = cc.rule_id "
        "WHERE cc.project_id=? ORDER BY cc.rule_id, cc.check_id",
        (project_id,),
    ).fetchall()
    from compliance.governance import calculation_is_current
    result = []
    for row in rows:
        d = dict(row)
        d['current'] = calculation_is_current(conn, project_id, row)
        if not d['current']:
            d['historical_status'] = d['status']
            d['status'] = 'NOT_EVALUATED'
            d['reason'] = 'STALE: recalculation and compliance rerun required. ' + (d.get('reason') or '')
        result.append(d)
    return result


def _assumption_rows(conn, project_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM assumptions WHERE project_id=? ORDER BY assumption_id", (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def _qaqc_rows(conn, project_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM qaqc_results WHERE project_id=? ORDER BY id", (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def generate_calculation_report(conn, project_id: int) -> dict:
    """Structured report data — the single source both the Markdown
    renderer below and any future PDF/DOCX renderer should read from."""
    calcs = _calculation_rows(conn, project_id)
    compliance = _compliance_rows(conn, project_id)

    calc_status_counts: dict[str, int] = {}
    for c in calcs:
        calc_status_counts[c["status"]] = calc_status_counts.get(c["status"], 0) + 1

    compliance_status_counts: dict[str, int] = {}
    for c in compliance:
        compliance_status_counts[c["status"]] = compliance_status_counts.get(c["status"], 0) + 1

    return {
        "governance": context(conn, project_id),
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "project": _project_row(conn, project_id),
        "design_basis": _design_basis_rows(conn, project_id),
        "calculations": calcs,
        "calculation_status_counts": calc_status_counts,
        "compliance": compliance,
        "compliance_status_counts": compliance_status_counts,
        "assumptions": _assumption_rows(conn, project_id),
        "qaqc": _qaqc_rows(conn, project_id),
    }


def _fmt(v, unit=None):
    if v is None:
        return "—"
    return f"{v} {unit}".strip() if unit else str(v)


def generate_calculation_report_markdown(conn, project_id: int) -> str:
    data = generate_calculation_report(conn, project_id)
    p = data["project"]
    lines = []

    lines.append(f"# Plumbing Design Calculation Report")
    lines.append("")
    lines.append(f"**Project:** {p.get('project_name', '—')}  ")
    lines.append(f"**Project No.:** {p.get('project_number') or '—'}  ")
    lines.append(f"**Location:** {p.get('project_location') or '—'}  ")
    lines.append(f"**Building type:** {p.get('building_type') or '—'}  ")
    lines.append(f"**Governing code:** {p.get('code_id') or '—'} {p.get('code_edition') or ''}  ")
    lines.append(f"**Design engineer:** {p.get('design_engineer') or '—'}  ")
    lines.append(f"**Revision:** {p.get('revision') or '—'}  ")
    lines.append(f"**Report generated:** {data['generated_at']}  ")
    lines.append("")
    lines.append(
        "> Every value below traces to a specific formula, code reference, and status. "
        "A completed calculation is not automatically compliant or approved — calculation "
        "success, code compliance, and engineer approval remain three separate things "
        "(see status column). Values marked FLAGGED, WARNING, or ASSUMED must be confirmed "
        "before this report is issued for construction."
    )
    lines.append("")

    g = data['governance']
    lines.append('## Code profile and verification')
    lines.append(f"**Review status:** {g['review_status']}")
    for issue in g['issues']:
        lines.append(f'- {issue}')
    if g['basis']:
        lines.append(f"**Profile:** {g['basis']['profile_id']} | **Basis revision:** {g['basis']['revision']}")
        lines.append(f"**Project adoption:** {g['basis']['basis_status']}")
    lines.append('Technical results and code/engineer approval are separate. Stale records require recalculation.')
    lines.append('')

    lines.append("## 1. Design Basis")
    if data["design_basis"]:
        lines.append("| Item | Value | Source | Status |")
        lines.append("|---|---|---|---|")
        for d in data["design_basis"]:
            lines.append(f"| {d['item_key']} | {_fmt(d['item_value'], d.get('unit'))} | "
                         f"{d['source_classification']} | {d['status']} |")
    else:
        lines.append("_No design-basis items recorded._")
    lines.append("")

    lines.append("## 2. Calculations")
    lines.append(f"Summary: " + ", ".join(f"{k}={v}" for k, v in sorted(data["calculation_status_counts"].items())) or "_None._")
    lines.append("")
    if data["calculations"]:
        lines.append("| Calc ID | Type | Formula | Result | Required | Selected | Technical status | Review status | Reference | Notes |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for c in data["calculations"]:
            lines.append(
                f"| {c['calc_id']} | {c['calc_type']} | {c['formula']} | "
                f"{_fmt(c['result_value'], c.get('result_unit'))} | {_fmt(c['required_value'])} | "
                f"{_fmt(c['selected_value'])} | {c['status']} | {c['review_status']} | {c.get('reference') or '—'} | {c.get('notes') or '—'} |"
            )
    else:
        lines.append("_No calculations recorded yet._")
    lines.append("")

    lines.append("## 3. Code Compliance")
    lines.append(f"Summary: " + ", ".join(f"{k}={v}" for k, v in sorted(data["compliance_status_counts"].items())) or "_Not run yet._")
    lines.append("")
    if data["compliance"]:
        lines.append("| Rule ID | Severity | Status | Reason |")
        lines.append("|---|---|---|---|")
        for c in data["compliance"]:
            lines.append(f"| {c['rule_id']} | {c['severity']} | {c['status']} | {c.get('reason') or '—'} |")
    else:
        lines.append("_Compliance check has not been run for this project yet._")
    lines.append("")

    lines.append("## 4. Assumptions")
    if data["assumptions"]:
        lines.append("| ID | Description | Value | Status |")
        lines.append("|---|---|---|---|")
        for a in data["assumptions"]:
            lines.append(f"| {a['assumption_id']} | {a['description']} | {a.get('value') or '—'} | {a['status']} |")
    else:
        lines.append("_No open assumptions recorded._")
    lines.append("")

    lines.append("## 5. QA/QC Dashboard")
    if data["qaqc"]:
        lines.append("| Check | Category | Status | Details |")
        lines.append("|---|---|---|---|")
        for q in data["qaqc"]:
            lines.append(f"| {q['check_name']} | {q['category']} | {q['status']} | {q['details']} |")
    else:
        lines.append("_QA/QC dashboard has not been run for this project yet — see QA/QC Dashboard page._")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    from database.db import get_connection
    conn = get_connection()
    pid_row = conn.execute("SELECT project_id FROM projects LIMIT 1").fetchone()
    if pid_row is None:
        print("No project found — run tests/demo_project.py first.")
    else:
        print(generate_calculation_report_markdown(conn, pid_row["project_id"]))
    conn.close()
