"""
tests/test_reports.py
----------------------------
Regression tests for Phase 6: reports/qaqc_dashboard.py and
reports/report_generator.py.
"""

import pytest

from database.db import init_db
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from compliance.engine import run_compliance_for_project
from database.load_design_tables import load_all_workbooks
from database.load_confirmed_additions import load_all_confirmed_additions
from calculations.hydraulics import hazen_williams_head_loss
from reports.qaqc_dashboard import run_qaqc
from reports.report_generator import generate_calculation_report, generate_calculation_report_markdown


def _project_with_data(tmp_path):
    conn = init_db(db_path=tmp_path / "test.db", reset=True)
    load_all_rules(conn)
    sync_predicate_flags(conn)
    load_all_workbooks(conn)
    load_all_confirmed_additions(conn)

    cur = conn.execute(
        """INSERT INTO projects (project_name, project_number, project_location, building_type,
             code_id, code_edition, design_engineer, revision, project_date)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        ("Test Project", "PRJ-T", "Riyadh", "Hospital", "SAUDI_SBC_701", "SBC701-2024",
         "Ahmed", "R0", "2026-09-01"),
    )
    project_id = cur.lastrowid
    conn.commit()

    r = hazen_williams_head_loss(flow_lps=2.5, internal_diameter_mm=50.0, length_m=40.0,
                                  c_factor=150, calc_id="CW-001")
    row = r.as_row(project_id, target_type="pipe", target_id="CW-P-001")
    conn.execute(
        """INSERT INTO calculations (calc_id, project_id, calc_type, target_type, target_id,
             formula, inputs_json, intermediate_json, result_value, result_unit,
             required_value, selected_value, status, code_rule_id, reference)
           VALUES (:calc_id,:project_id,:calc_type,:target_type,:target_id,:formula,
             :inputs_json,:intermediate_json,:result_value,:result_unit,
             :required_value,:selected_value,:status,:code_rule_id,:reference)""",
        row,
    )
    conn.commit()

    run_compliance_for_project(conn, project_id, "SAUDI_SBC_701")

    conn.execute(
        """INSERT INTO design_basis_items (project_id, item_key, item_value, unit,
             source_classification, status) VALUES (?,?,?,?,?,?)""",
        (project_id, "rainfall_return_period_yr", "10", "yr", "PROJECT", "PENDING"),
    )
    conn.execute(
        """INSERT INTO assumptions (assumption_id, project_id, description, value, status)
           VALUES (?,?,?,?,?)""",
        ("A-001", project_id, "Assumed occupancy factor", "0.8", "PENDING_ENGINEER_APPROVAL"),
    )
    conn.commit()

    return conn, project_id


def test_qaqc_dashboard_runs_and_persists(tmp_path):
    conn, project_id = _project_with_data(tmp_path)
    results = run_qaqc(conn, project_id)
    names = {r["check_name"] for r in results}
    assert "Calculation status summary" in names
    assert "Compliance rule status summary" in names
    assert "Design-basis approval status" in names
    assert "Assumption approval status" in names

    persisted = conn.execute("SELECT COUNT(*) AS n FROM qaqc_results WHERE project_id=?",
                              (project_id,)).fetchone()["n"]
    assert persisted == len(results)


def test_qaqc_dashboard_flags_pending_design_basis_and_assumptions(tmp_path):
    conn, project_id = _project_with_data(tmp_path)
    results = {r["check_name"]: r for r in run_qaqc(conn, project_id)}
    assert results["Design-basis approval status"]["status"] == "WARNING"
    assert "rainfall_return_period_yr" in results["Design-basis approval status"]["details"]
    assert results["Assumption approval status"]["status"] == "WARNING"
    assert "A-001" in results["Assumption approval status"]["details"]


def test_qaqc_dashboard_rerun_clears_previous_snapshot(tmp_path):
    conn, project_id = _project_with_data(tmp_path)
    run_qaqc(conn, project_id)
    n1 = conn.execute("SELECT COUNT(*) AS n FROM qaqc_results WHERE project_id=?",
                       (project_id,)).fetchone()["n"]
    run_qaqc(conn, project_id)
    n2 = conn.execute("SELECT COUNT(*) AS n FROM qaqc_results WHERE project_id=?",
                       (project_id,)).fetchone()["n"]
    assert n1 == n2  # not accumulating duplicate rows on rerun


def test_report_generator_structure(tmp_path):
    conn, project_id = _project_with_data(tmp_path)
    run_qaqc(conn, project_id)
    data = generate_calculation_report(conn, project_id)
    assert data["project"]["project_name"] == "Test Project"
    assert len(data["calculations"]) == 1
    assert data["calculations"][0]["calc_id"] == "CW-001"
    assert len(data["compliance"]) == 8  # SAUDI_SBC_701 has 8 rules
    assert len(data["assumptions"]) == 1
    assert len(data["qaqc"]) == 7


def test_report_generator_markdown_contains_key_sections(tmp_path):
    conn, project_id = _project_with_data(tmp_path)
    run_qaqc(conn, project_id)
    md = generate_calculation_report_markdown(conn, project_id)
    assert "# Plumbing Design Calculation Report" in md
    assert "Test Project" in md
    assert "## 1. Design Basis" in md
    assert "## 2. Calculations" in md
    assert "## 3. Code Compliance" in md
    assert "## 4. Assumptions" in md
    assert "## 5. QA/QC Dashboard" in md
    assert "CW-001" in md


def test_report_generator_handles_empty_project(tmp_path):
    """A brand-new project with nothing calculated yet must not crash the report."""
    conn = init_db(db_path=tmp_path / "test.db", reset=True)
    load_all_rules(conn)  # populates `codes` — project_id has an FK on code_id
    cur = conn.execute(
        "INSERT INTO projects (project_name, building_type, code_id) VALUES (?,?,?)",
        ("Empty Project", "Office", "IPC"),
    )
    project_id = cur.lastrowid
    conn.commit()
    md = generate_calculation_report_markdown(conn, project_id)
    assert "Empty Project" in md
    assert "_No calculations recorded yet._" in md
