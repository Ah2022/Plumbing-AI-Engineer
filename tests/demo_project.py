"""
tests/demo_project.py
-----------------------
End-to-end smoke test / demo. Run with:

    cd plumbing_engine
    python -m tests.demo_project

Exercises the real pipeline against the supplied code-rule data:
  1. Initialize DB + load all 32 rules from database/codes/
  2. Create a demo project (Riyadh hospital, SAUDI_SBC_701)
  3. Run a real hydraulic calculation (Hazen-Williams) and store it
  4. Run the compliance engine against the loaded SBC 701 rules
  5. Deliberately show a MissingCodeDataError for a code-dependent
     calculation (proves the "never invent a value" behaviour works)
"""

from __future__ import annotations

from database.db import init_db
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from compliance.engine import run_compliance_for_project
from database.load_design_tables import load_all_workbooks
from database.load_confirmed_additions import load_all_confirmed_additions
from calculations.hydraulics import hazen_williams_head_loss
from calculations.water import check_velocity_limit, total_fixture_units, size_pipe_from_demand
from calculations.hot_water import hot_water_demand
from calculations.tanks import size_hot_water_storage_tank_from_demand
from calculations.pumps import select_pump_duty
from calculations.stormwater import design_rainfall_intensity, size_roof_drain, size_storm_drain_pipe
from calculations.hydraulics import rational_method_peak_flow
from reports.qaqc_dashboard import run_qaqc
from reports.report_generator import generate_calculation_report_markdown
from bim.schemas import empty_extract_payload
from bim.exchange import import_revit_extract, export_results_for_revit
from models import MissingCodeDataError


def main():
    conn = init_db(reset=True)

    print("=" * 70)
    print("STEP 1 — Load code rules from database/codes/")
    print("=" * 70)
    summary = load_all_rules(conn)
    for code_id, n in summary.items():
        print(f"  {code_id:16s} {n:3d} rules loaded")
    sync_predicate_flags(conn)

    print("\n" + "=" * 70)
    print("STEP 1b — Load numeric design tables (Code_Data.zip workbooks)")
    print("=" * 70)
    dt_summary = load_all_workbooks(conn)
    for code_id, s in dt_summary.items():
        if "error" in s:
            print(f"  {code_id:16s} {s['error']}")
        else:
            print(f"  {code_id:16s} {s['tables_loaded']:2d} tables, {s['rows_loaded']:4d} values "
                  f"({s['flagged_rows']} flagged)")

    print("\n" + "=" * 70)
    print("STEP 1c — Load Ahmed's independently-verified additions")
    print("=" * 70)
    conf_summary = load_all_confirmed_additions(conn)
    print(f"  Riyadh rainfall depth (Al-Saleh 1997): {conf_summary['riyadh_rainfall_values']} values")
    print(f"  PPR-PN16 velocity (Aquatherm mfr.)    : {conf_summary['ppr_pn16_values']} values")

    print("\n" + "=" * 70)
    print("STEP 2 — Create a demo project")
    print("=" * 70)
    cur = conn.execute(
        """INSERT INTO projects (project_name, project_number, project_location, building_type,
             gross_area_m2, num_floors, occupancy, design_stage, code_id, code_edition,
             design_engineer, revision, project_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        ("Demo Hospital - Riyadh", "PRJ-001", "Riyadh, KSA", "Hospital",
         25000, 6, 1200, "DD", "SAUDI_SBC_701", "SBC 701-2024",
         "Ahmed", "R0", "2026-08-30"),
    )
    project_id = cur.lastrowid
    conn.commit()
    print(f"  Created project_id={project_id} (SAUDI_SBC_701, Hospital, Riyadh)")

    print("\n" + "=" * 70)
    print("STEP 3 — Run a real hydraulic calculation (Hazen-Williams)")
    print("=" * 70)
    hw_result = hazen_williams_head_loss(
        flow_lps=2.5, internal_diameter_mm=50.0, length_m=40.0, c_factor=150, calc_id="CW-001"
    )
    print(f"  {hw_result.formula}")
    print(f"  Result: {hw_result.result_value} {hw_result.result_unit}  "
          f"(status={hw_result.status})")
    row = hw_result.as_row(project_id, target_type="pipe", target_id="CW-P-001")
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
    print("  Stored to `calculations` table.")

    print("\n" + "=" * 70)
    print("STEP 4 — Run the compliance engine (SAUDI_SBC_701, 8 rules)")
    print("=" * 70)
    results = run_compliance_for_project(conn, project_id, "SAUDI_SBC_701")
    for r in results:
        print(f"  {r['rule_id']:14s} [{r['severity']:7s}] -> {r['status']:14s} {r['reason'] or ''}")

    print("\n" + "=" * 70)
    print("STEP 5 — Real code-sourced velocity check (Phase 2)")
    print("=" * 70)
    v_ipc = check_velocity_limit(
        conn, project_id, "IPC", pipe_id="CW-P-002",
        flow_lps=1.0, internal_diameter_mm=25.0, calc_id="CW-002",
    )
    print(f"  IPC: velocity={v_ipc.result_value} m/s vs limit={v_ipc.required_value} m/s "
          f"-> {v_ipc.status}  [{v_ipc.reference}]")

    print("\n  SAUDI_SBC_701 has NO stated velocity limit (documented gap in the source data).")
    try:
        check_velocity_limit(conn, project_id, "SAUDI_SBC_701", "CW-P-003", 1.0, 25.0, "CW-003")
        print("  UNEXPECTED: completed without a code-sourced limit.")
    except MissingCodeDataError as e:
        print(f"  Correctly stopped without a fallback: {e}")

    v_fallback = check_velocity_limit(
        conn, project_id, "SAUDI_SBC_701", "CW-P-003", 1.0, 25.0, "CW-004",
        allow_fallback_code="IPC",
    )
    print(f"  With explicit allow_fallback_code='IPC': -> {v_fallback.status}  "
          f"(confidence={v_fallback.status}, {v_fallback.notes})")

    print("\n" + "=" * 70)
    print("STEP 6 — Real fixture-unit demand calc (IPC fixture table)")
    print("=" * 70)
    fixtures = [
        {"fixture_name": "Water closet", "occupancy": "Public", "control": "Flushometer", "quantity": 40},
        {"fixture_name": "Lavatory", "occupancy": "Public", "control": "Faucet", "quantity": 30},
    ]
    fu_result = total_fixture_units(conn, "IPC", fixtures)
    print(f"  40x Water closet (Public/Flushometer) + 30x Lavatory (Public/Faucet)")
    print(f"  -> total cold-water fixture units = {fu_result['total_cold_fu']} "
          f"(confidence={fu_result['confidence']})")

    print("\n" + "=" * 70)
    print("STEP 7 — Pipe sizing from demand (completes Phase 2)")
    print("=" * 70)
    pipe_result = size_pipe_from_demand(conn, "SAUDI_SBC_701", total_wsfu=12, calc_id="CW-005",
                                         control_type="flush_tank", material="PPR")
    print(f"  12 WSFU -> demand={pipe_result.intermediate['demand_lpm']} L/min -> "
          f"required diameter={pipe_result.result_value} mm")

    print("\n" + "=" * 70)
    print("STEP 8 — Hot water demand, storage, and pump duty (Phase 4)")
    print("=" * 70)
    hw_fixtures = [{"fixture_name": "Showers", "quantity": 20}, {"fixture_name": "Basins, private lavatory", "quantity": 40}]
    hw_result = hot_water_demand(conn, hw_fixtures, calc_id="HW-001")
    print(f"  20 showers + 40 lavatories -> design hourly demand = {hw_result.result_value} {hw_result.result_unit}")
    tank_result = size_hot_water_storage_tank_from_demand(hw_result, calc_id="TK-001")
    print(f"  -> storage tank = {tank_result.result_value} {tank_result.result_unit}")
    pump_result = select_pump_duty(design_flow_lps=5.0, static_head_m=20, friction_loss_m=3,
                                    fitting_loss_m=1, equipment_loss_m=2, required_residual_head_m=15,
                                    efficiency=0.7, calc_id="PMP-001")
    print(f"  Pump duty: 5 L/s @ {pump_result.intermediate['tdh_m']}m TDH -> {pump_result.result_value} kW")

    print("\n" + "=" * 70)
    print("STEP 9 — Stormwater: rainfall intensity -> Rational Method -> roof")
    print("         drain (leader) sizing -> storm drain pipe sizing (Phase 5)")
    print("=" * 70)
    intensity_result = design_rainfall_intensity(conn, "SAUDI_SBC_701", 10, "15 min", "ST-001")
    print(f"  10-yr, 15-min storm, Riyadh station -> intensity = "
          f"{intensity_result.result_value} {intensity_result.result_unit}  [{intensity_result.reference}]")
    peak_flow_result = rational_method_peak_flow(0.9, intensity_result.result_value, 500, "ST-002")
    print(f"  C=0.9, 500 m2 roof -> peak flow = {peak_flow_result.result_value} {peak_flow_result.result_unit}")
    leader_result = size_roof_drain(conn, "SAUDI_SBC_701", 500, intensity_result.result_value, "ST-003")
    print(f"  -> leader size = {leader_result.result_value} {leader_result.result_unit}  [{leader_result.notes}]")
    storm_pipe_result = size_storm_drain_pipe(conn, "SAUDI_SBC_701", peak_flow_result.result_value, "ST-004",
                                               orientation="vertical")
    print(f"  -> storm drain pipe (vertical) = {storm_pipe_result.result_value} {storm_pipe_result.result_unit}")
    for r in (intensity_result, peak_flow_result, leader_result, storm_pipe_result):
        row = r.as_row(project_id, target_type="site", target_id="STORM-001")
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

    print("\n" + "=" * 70)
    print("STEP 10 — QA/QC dashboard + calculation report (Phase 6)")
    print("=" * 70)
    qaqc_results = run_qaqc(conn, project_id)
    for r in qaqc_results:
        print(f"  [{r['status']:12s}] {r['check_name']:38s} {r['details'][:80]}")
    report_md = generate_calculation_report_markdown(conn, project_id)
    print(f"\n  Calculation report generated: {len(report_md)} characters "
          f"({report_md.count(chr(10)) + 1} lines). First line: {report_md.splitlines()[0]!r}")

    print("\n" + "=" * 70)
    print("STEP 11 — Revit exchange round-trip, simulated (Phase 7)")
    print("=" * 70)
    print("  bim/pyrevit/ scripts need a live Revit session to actually run — this step")
    print("  simulates what they produce/consume so the engine-side half is proven end to end.")
    mock_extract = empty_extract_payload("SMC3-Plumbing.rvt", "2026-09-09T12:00:00")
    mock_extract["pipes"].append({
        "revit_element_id": "987654", "system": "cold_water",
        "length_m": 40.0, "nominal_diameter_mm": 50.0, "level": "L01",
    })
    counts = import_revit_extract(conn, project_id, mock_extract)
    print(f"  Simulated extract imported: {counts}")
    linked_pipe = conn.execute(
        "SELECT pipe_id FROM pipes WHERE project_id=? AND revit_element_id='987654'", (project_id,)
    ).fetchone()
    linked_hw = hazen_williams_head_loss(flow_lps=2.5, internal_diameter_mm=50.0, length_m=40.0,
                                          c_factor=150, calc_id="CW-006")
    row = linked_hw.as_row(project_id, target_type="pipe", target_id=linked_pipe["pipe_id"])
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
    results_payload = export_results_for_revit(conn, project_id)
    print(f"  Results payload for the pyRevit writer script: "
          f"{results_payload['results']['987654']}")

    conn.close()
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
