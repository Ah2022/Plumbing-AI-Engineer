"""
app/streamlit_app.py
-----------------------
Run with:  streamlit run app/streamlit_app.py   (from the plumbing_engine/ directory)

Navigation follows the spec's own UI section (Section 35): PROJECT,
DESIGN BASIS, FIXTURES, WATER, DRAINAGE, VENT, CODE CHECK, QA/QC, REPORT.
Only pages backed by real, tested calculation logic are enabled — Hot
Water / Storm / Tanks / Pumps are shown as "not yet available" (Phase 4/5)
rather than faked with placeholder math.

Every result shown is a CalculationResult: formula, inputs, required vs
selected, status, and code reference are always displayed together — no
number appears without its full trace, matching the spec's core principle
(Section 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st

from database.db import init_db, get_connection, get_db_path
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags
from compliance.engine import run_compliance_for_project
from database.load_design_tables import load_all_workbooks
from database.load_confirmed_additions import load_all_confirmed_additions
from calculations.water import check_velocity_limit, total_fixture_units, size_pipe_from_demand
from calculations.drainage import size_drainage_pipe, check_min_slope, check_drainage_velocity
from calculations.vent import size_vent_pipe, size_vent_pipe_multidim
from calculations.hot_water import hot_water_demand, check_hot_water_temperature, heater_capacity, TEMPERATURE_CHECKS
from calculations.tanks import size_domestic_water_tank, size_hot_water_storage_tank_from_demand
from calculations.pumps import select_pump_duty
from database.design_table_api import (list_water_fixture_unit_choices,
    list_drainage_fixture_unit_choices, list_hot_water_demand_choices)
from app.fixture_schedule import fixture_schedule
from calculations.stormwater import design_rainfall_intensity, size_roof_drain, size_storm_drain_pipe
from calculations.hydraulics import rational_method_peak_flow
from reports.qaqc_dashboard import run_qaqc
from reports.report_generator import generate_calculation_report_markdown
from models import MissingCodeDataError
from app.db_helpers import save_calculation, next_calc_id, status_badge
from app.code_profiles_page import page_code_profiles, clear_result_session
from app.network_page import page_network_review
from compliance.governance import profile_for_code, set_basis, context, seed_review_inventory
from database.governance_schema import ensure_governance_schema

st.set_page_config(page_title="Plumbing Design Engine", layout="wide")

DB_PATH = get_db_path()


def bootstrap_db():
    """First run only: create the DB and load rules + design tables + confirmed additions.
    Deliberately NOT cached with @st.cache_resource — that would cache the
    file-existence check itself and skip re-initializing if the DB file is
    ever removed while the process is still alive. The existence check below
    already makes repeat calls cheap."""
    if not DB_PATH.exists():
        conn = init_db(DB_PATH)
        load_all_rules(conn)
        sync_predicate_flags(conn)
        load_all_workbooks(conn)
        load_all_confirmed_additions(conn)
        conn.close()
    return True


def get_conn():
    bootstrap_db()
    # check_same_thread=False: Streamlit can run script reruns on different
    # worker threads within one user session. Access here is sequential per
    # session (Streamlit never runs two reruns of the same session
    # concurrently), so sharing one connection across those threads is safe.
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    ensure_governance_schema(conn)
    seed_review_inventory(conn)
    return conn


def get_codes(conn):
    rows = conn.execute("SELECT code_id, code_name FROM codes ORDER BY code_id").fetchall()
    return {r["code_id"]: r["code_name"] for r in rows}


def result_to_row(r) -> dict:
    return {
        "calc_id": r.calc_id,
        "status": status_badge(r.status),
        "review_status": getattr(r, 'review_status', 'REVIEW_REQUIRED'),
        "result": f"{r.result_value} {r.result_unit or ''}".strip(),
        "required": r.required_value,
        "selected": r.selected_value,
        "formula": r.formula,
        "reference": r.reference,
        "notes": r.notes,
    }


def show_result_table(r) -> None:
    """Render a CalculationResult as a one-column table. Cast to str first —
    a mixed float/string single column trips PyArrow's dataframe serializer."""
    row = {k: ("" if v is None else str(v)) for k, v in result_to_row(r).items()}
    st.table(pd.DataFrame([row]).T.rename(columns={0: "value"}))


# ------------------------------------------------------------------ PROJECT

def page_project():
    st.header("Project")
    conn = st.session_state.conn
    codes = get_codes(conn)

    existing = conn.execute("SELECT project_id, project_name, code_id FROM projects ORDER BY project_id").fetchall()
    if existing:
        st.subheader("Open an existing project")
        options = {f"#{r['project_id']} — {r['project_name']} ({r['code_id']})": r["project_id"] for r in existing}
        choice = st.selectbox("Project", ["(new project)"] + list(options.keys()))
        if choice != "(new project)":
            if st.session_state.get('project_id') != options[choice]:
                clear_result_session()
            st.session_state.project_id = options[choice]
            st.success(f"Active project: {choice}")

    st.subheader("Create a new project")
    with st.form("new_project"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Project name", "SMC 3 - Specialized Medical Centre")
            number = st.text_input("Project number", "PRJ-001")
            location = st.text_input("Location", "Riyadh, KSA")
            building_type = st.selectbox("Building type", [
                "Residential", "Apartment", "Hotel", "Hospital", "Office", "School",
                "University", "Shopping Mall", "Restaurant", "Industrial", "Warehouse",
                "Mixed Use", "Other",
            ], index=3)
            code_id = st.selectbox("Applicable code", list(codes.keys()),
                                    format_func=lambda c: f"{c} — {codes[c]}",
                                    index=list(codes.keys()).index("IPC") if "IPC" in codes else 0)
        with col2:
            gross_area = st.number_input("Gross area (m²)", min_value=0.0, value=25000.0)
            floors = st.number_input("Number of floors", min_value=0, value=6, step=1)
            occupancy = st.number_input("Occupancy (persons)", min_value=0, value=1200, step=1)
            engineer = st.text_input("Design engineer", "Ahmed")
            revision = st.text_input("Revision", "R0")

        submitted = st.form_submit_button("Create project")
        if submitted:
            cur = conn.execute(
                """INSERT INTO projects (project_name, project_number, project_location, building_type,
                     gross_area_m2, num_floors, occupancy, design_stage, code_id, design_engineer, revision)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (name, number, location, building_type, gross_area, floors, occupancy,
                 "DD", code_id, engineer, revision),
            )
            conn.commit()
            st.session_state.project_id = cur.lastrowid
            clear_result_session()
            selected_profile = profile_for_code(code_id)
            if selected_profile:
                set_basis(conn, cur.lastrowid, selected_profile['profile_id'],
                          dict(occupancy=building_type, systems=['water'], units='SI'),
                          engineer or 'Project creator')
            st.success(f"Created project #{cur.lastrowid}")
            st.rerun()


# -------------------------------------------------------------- DESIGN BASIS

def page_design_basis():
    st.header("Design Basis")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return

    items = conn.execute(
        "SELECT * FROM design_basis_items WHERE project_id = ? ORDER BY id", (project_id,)
    ).fetchall()
    if items:
        df = pd.DataFrame([dict(i) for i in items])
        st.dataframe(df[["item_key", "item_value", "unit", "source_classification", "status"]],
                     width='stretch')

        st.subheader("Approve / reject an item")
        item_choice = st.selectbox("Item", [i["item_key"] for i in items])
        colA, colB = st.columns(2)
        if colA.button("✅ Approve"):
            conn.execute(
                "UPDATE design_basis_items SET status='APPROVED' WHERE project_id=? AND item_key=?",
                (project_id, item_choice),
            )
            conn.commit()
            st.rerun()
        if colB.button("❌ Reject"):
            conn.execute(
                "UPDATE design_basis_items SET status='REJECTED' WHERE project_id=? AND item_key=?",
                (project_id, item_choice),
            )
            conn.commit()
            st.rerun()
    else:
        st.info("No design basis items yet.")

    st.subheader("Add a design basis item")
    with st.form("new_basis_item"):
        key = st.text_input("Item key (e.g. static_pressure_psi, rainfall_intensity_mm_hr)")
        value = st.text_input("Value")
        unit = st.text_input("Unit", "")
        source = st.selectbox("Source classification", ["CODE", "PROJECT", "USER_INPUT", "MANUFACTURER", "ASSUMED"])
        if st.form_submit_button("Add") and key and value:
            conn.execute(
                """INSERT INTO design_basis_items (project_id, item_key, item_value, unit, source_classification, status)
                   VALUES (?, ?, ?, ?, ?, 'PENDING')""",
                (project_id, key, value, unit, source),
            )
            conn.commit()
            st.rerun()


# --------------------------------------------------------- FIXTURES & WATER

def page_water():
    st.header("Fixtures & Cold Water")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    code_id = _project_code(conn, project_id)
    st.caption(f"Active code: **{code_id}**")

    tab1, tab2, tab3 = st.tabs(["Fixture-unit demand", "Velocity check", "Pipe sizing from demand"])

    with tab1:
        st.write("Pick fixtures from the code's own fixture-unit table — the WSFU value shown "
                 "is the real table value, not typed in, so there's no risk of a name mismatch.")
        choices = list_water_fixture_unit_choices(conn, code_id)
        if choices:
            with st.form("fixture_row"):
                picked_label = st.selectbox("Fixture", [c["label"] for c in choices])
                qty = st.number_input("Quantity", min_value=1, value=1, step=1)
                add = st.form_submit_button("Add to list")
                if add:
                    c = next(c for c in choices if c["label"] == picked_label)
                    st.session_state.setdefault("fixture_list", []).append({
                        "fixture_name": c["fixture_name"], "occupancy": c["occupancy"],
                        "control": c["control"], "quantity": qty,
                        "wsfu_value": c["wsfu_value"], "confidence": c["confidence"],
                    })
        else:
            st.warning(
                f"**{code_id}**'s own fixture-unit table doesn't have water-supply fixture-unit "
                f"values loaded yet (this is currently only true for EGYPT_LOCAL, which has no "
                f"'1_Fixture_Units' table at all). Enter a value manually below only if you have "
                f"it from another traceable source (cite it in the project notes) — this page "
                f"won't invent one for you."
            )
            with st.form("fixture_row_manual"):
                c1, c2, c3, c4, c5 = st.columns(5)
                fname = c1.text_input("Fixture name", "Water closet")
                occ = c2.text_input("Occupancy", "")
                ctrl = c3.text_input("Control", "")
                qty = c4.number_input("Quantity", min_value=1, value=1, step=1)
                wsfu_manual = c5.number_input("WSFU value", min_value=0.0, value=0.0)
                add2 = st.form_submit_button("Add to list")
                if add2:
                    st.session_state.setdefault("fixture_list", []).append({
                        "fixture_name": fname, "occupancy": occ or None, "control": ctrl or None,
                        "quantity": qty, "wsfu_value": wsfu_manual if wsfu_manual > 0 else None,
                        "confidence": "FLAGGED" if wsfu_manual > 0 else None,
                    })

        fixtures = st.session_state.get("fixture_list", [])
        if fixtures:
            st.dataframe(pd.DataFrame(fixtures), width='stretch')
            if st.button("Clear list"):
                st.session_state["fixture_list"] = []
                st.rerun()
            if st.button("Calculate total fixture units"):
                try:
                    result = total_fixture_units(conn, code_id, fixtures)
                    st.success(f"Total cold-water FU = **{result['total_cold_fu']}** "
                               f"(confidence: {result['confidence']})")
                except (MissingCodeDataError, ValueError) as e:
                    st.error(str(e))

    with tab2:
        with st.form("velocity_check"):
            c1, c2, c3 = st.columns(3)
            flow = c1.number_input("Flow (L/s)", min_value=0.0, value=1.0)
            dia = c2.number_input("Internal diameter (mm)", min_value=1.0, value=25.0)
            material = c3.text_input("Material (optional, e.g. PPR)", "")
            fallback = st.checkbox(f"Allow explicit fallback to IPC if {code_id} has no stated limit")
            run = st.form_submit_button("Run velocity check")
        if run:
            try:
                calc_id = next_calc_id(conn, project_id, "cold_water_velocity_check")
                r = check_velocity_limit(
                    conn, project_id, code_id, pipe_id="CW-P-UI", flow_lps=flow,
                    internal_diameter_mm=dia, calc_id=calc_id,
                    material=material or None,
                    allow_fallback_code="IPC" if fallback else None,
                )
                save_calculation(conn, project_id, r)
                st.markdown(f"### {status_badge(r.status)}")
                show_result_table(r)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))

    with tab3:
        st.caption("Completes the chain: WSFU -> design flow (Hunter's Curve, interpolated) -> "
                   "required internal diameter. Note: this returns the hydraulically-required "
                   "diameter, not a manufacturer nominal size — no pipe-dimension catalog is loaded yet.")
        with st.form("pipe_from_demand"):
            c1, c2, c3 = st.columns(3)
            wsfu = c1.number_input("Total WSFU", min_value=0.0, value=12.0)
            control = c2.selectbox("Control type", ["flush_tank", "flush_valve"])
            material2 = c3.text_input("Material (optional, e.g. PPR)", "PPR", key="pipe_sizing_material")
            fixture_ctx = st.text_input("Fixture minimum-size context (optional, e.g. 'Water closet, flushometer valve')", "")
            fallback2 = st.checkbox("Allow velocity-limit fallback to IPC", key="pipe_sizing_fallback")
            run3 = st.form_submit_button("Size the pipe from demand")
        if run3:
            try:
                calc_id = next_calc_id(conn, project_id, "cold_water_pipe_sizing")
                r3 = size_pipe_from_demand(
                    conn, code_id, wsfu, calc_id, control_type=control,
                    material=material2 or None, fixture_min_size_context=fixture_ctx or None,
                    allow_velocity_fallback_code="IPC" if fallback2 else None,
                )
                save_calculation(conn, project_id, r3)
                st.markdown(f"### {status_badge(r3.status)} — {r3.result_value} mm required")
                show_result_table(r3)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))


# ------------------------------------------------------------ DRAINAGE/VENT

def page_drainage_vent():
    st.header("Drainage & Vent")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    code_id = _project_code(conn, project_id)
    st.caption(f"Active code: **{code_id}**")

    tab1, tab2, tab3, tab4 = st.tabs(["Drainage sizing", "Min slope check", "Vent sizing (simple)", "Vent sizing (IPC Table 906.1)"])

    with tab1:
        schedule, schedule_dfu = fixture_schedule(conn, project_id, code_id, 'Drainage',
            list_drainage_fixture_unit_choices(conn, code_id), 'DFU')
        use_schedule = st.checkbox('Use fixture list for drainage sizing', value=bool(schedule),
                                   disabled=not schedule)
        with st.form("drainage_sizing"):
            dfu = st.number_input("Manual total DFU", min_value=0.0, value=6.0, disabled=use_schedule,
                                  help="Ignored while the fixture list is selected.")
            context = st.selectbox("Context", [
                "horizontal_branch", "stack_le3_branch_intervals",
                "stack_gt3_branch_intervals", "branch_interval",
            ])
            run = st.form_submit_button("Size the pipe")
        if run:
            try:
                calc_id = next_calc_id(conn, project_id, "drainage_pipe_sizing")
                r = size_drainage_pipe(conn, code_id, schedule_dfu if use_schedule else dfu, context, calc_id)
                if use_schedule:
                    r.inputs['fixture_schedule'] = schedule
                save_calculation(conn, project_id, r)
                st.markdown(f"### {status_badge(r.status)} — {r.result_value} {r.result_unit}")
                show_result_table(r)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))

    with tab2:
        with st.form("min_slope"):
            size_mm = st.number_input("Pipe size (mm)", min_value=1.0, value=100.0)
            slope = st.number_input("Selected slope (%)", min_value=0.0, value=1.0, step=0.1)
            fallback = st.checkbox("Allow fallback to IPC")
            run = st.form_submit_button("Check slope")
        if run:
            try:
                calc_id = next_calc_id(conn, project_id, "drainage_min_slope_check")
                r = check_min_slope(conn, code_id, size_mm, slope, calc_id,
                                     allow_fallback_code="IPC" if fallback else None)
                save_calculation(conn, project_id, r)
                st.markdown(f"### {status_badge(r.status)}")
                show_result_table(r)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))

    with tab3:
        with st.form("vent_simple"):
            dfu = st.number_input("Total DFU", min_value=0.0, value=4.0, key="vent_dfu")
            run = st.form_submit_button("Size the vent")
        if run:
            try:
                calc_id = next_calc_id(conn, project_id, "vent_pipe_sizing")
                r = size_vent_pipe(conn, code_id, dfu, calc_id)
                save_calculation(conn, project_id, r)
                st.markdown(f"### {status_badge(r.status)} — {r.result_value} {r.result_unit}")
                show_result_table(r)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))
                st.caption("IPC has no simple DFU table — use the 'Vent sizing (IPC Table 906.1)' tab instead.")

    with tab4:
        st.caption("For codes whose vent table is multi-dimensional (currently: IPC Table 906.1 only). "
                   "SAUDI_SBC_701's own Table 906 was not independently re-extractable — this is the "
                   "confirmed fallback per docs/ARCHITECTURE.md Section 0b.")
        with st.form("vent_multidim"):
            stack = st.number_input("Stack size (inches)", min_value=1.0, value=4.0)
            fu = st.number_input("Fixture units", min_value=0.0, value=200.0)
            length = st.number_input("Developed length (ft)", min_value=0.0, value=90.0)
            run = st.form_submit_button("Size the vent (IPC Table 906.1)")
        if run:
            try:
                calc_id = next_calc_id(conn, project_id, "vent_pipe_sizing")
                r = size_vent_pipe_multidim(conn, "IPC", stack, fu, length, calc_id)
                save_calculation(conn, project_id, r)
                st.markdown(f"### {status_badge(r.status)} — {r.result_value} {r.result_unit}")
                show_result_table(r)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))


# ------------------------------------------------------------------ HOT WATER

def page_hot_water():
    st.header("Hot Water")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    st.caption("Demand/storage factors: ASPE Table 6-1 (confirmed by Ahmed as final for codes "
              "with no factors of their own). Temperature limits: IPC's confirmed hospital-specific "
              "figures — directly relevant to SMC-3.")

    tab1, tab2, tab3 = st.tabs(["Demand & storage", "Temperature checks", "Heater capacity"])

    with tab1:
        code_id = _project_code(conn, project_id)
        with st.expander('Hot-water fixture units (WSFU)', expanded=True):
            fixture_schedule(conn, project_id, code_id, 'Hot-water supply',
                list_water_fixture_unit_choices(conn, code_id, service='hot'), 'hot WSFU')
            st.caption('Hot WSFU supports supply-pipe demand assessment. It is separate from the GPH method below.')
        st.caption('Hourly demand rates below use the ASPE hospital method held in the IPC workbook, including for projects using another code. Review that method against the project basis.')
        hw_fixtures, connected_gph = fixture_schedule(conn, project_id, code_id, 'Hot-water demand',
            list_hot_water_demand_choices(conn), 'GPH')
        if hw_fixtures:
            if st.button("Calculate hot water demand & storage"):
                try:
                    calc_id = next_calc_id(conn, project_id, "hot_water_demand")
                    r = hot_water_demand(conn, hw_fixtures, calc_id)
                    save_calculation(conn, project_id, r)
                    st.markdown(f"### Design hourly demand: {r.result_value} {r.result_unit}")
                    show_result_table(r)
                    tk_calc_id = next_calc_id(conn, project_id, "tank_sizing")
                    tk = size_hot_water_storage_tank_from_demand(r, tk_calc_id)
                    save_calculation(conn, project_id, tk)
                    st.markdown(f"### Storage tank: {tk.result_value} {tk.result_unit}")
                except (MissingCodeDataError, ValueError) as e:
                    st.error(str(e))

    with tab2:
        with st.form("hw_temp_check"):
            check_type = st.selectbox("Check", list(TEMPERATURE_CHECKS.keys()))
            temp = st.number_input("Selected temperature (°C)", min_value=0.0, value=46.0)
            run = st.form_submit_button("Check")
        if run:
            try:
                calc_id = next_calc_id(conn, project_id, "hot_water_temperature_check")
                r = check_hot_water_temperature(conn, check_type, temp, calc_id)
                save_calculation(conn, project_id, r)
                st.markdown(f"### {status_badge(r.status)}")
                show_result_table(r)
            except (MissingCodeDataError, ValueError) as e:
                st.error(str(e))

    with tab3:
        with st.form("heater_capacity"):
            c1, c2, c3 = st.columns(3)
            mdot = c1.number_input("Mass flow (kg/s)", min_value=0.0, value=0.5)
            cold_t = c2.number_input("Cold water temp (°C)", value=15.0)
            hot_t = c3.number_input("Hot water temp (°C)", value=60.0)
            run = st.form_submit_button("Calculate heater capacity")
        if run:
            calc_id = next_calc_id(conn, project_id, "hot_water_heater_capacity")
            r = heater_capacity(mdot, cold_t, hot_t, calc_id)
            save_calculation(conn, project_id, r)
            st.markdown(f"### {r.result_value} {r.result_unit}")
            show_result_table(r)


# ------------------------------------------------------------------ TANKS

def page_tanks():
    st.header("Tanks")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    st.caption("Domestic cold-water tank sizing. storage_duration_hr should come from an "
              "APPROVED Design Basis entry — enter it here for now.")

    with st.form("tank_sizing"):
        c1, c2, c3 = st.columns(3)
        demand = c1.number_input("Average daily demand (L/s)", min_value=0.0, value=5.0)
        duration = c2.number_input("Storage duration (hr)", min_value=0.0, value=4.0)
        freeboard = c3.number_input("Freeboard (%)", min_value=0.0, value=10.0)
        run = st.form_submit_button("Size the tank")
    if run:
        calc_id = next_calc_id(conn, project_id, "tank_sizing")
        r = size_domestic_water_tank(demand, duration, calc_id, freeboard_pct=freeboard)
        save_calculation(conn, project_id, r)
        st.markdown(f"### Required: {r.required_value} m³ — Selected (with freeboard): {r.selected_value} m³")
        show_result_table(r)


# ------------------------------------------------------------------ PUMPS

def page_pumps():
    st.header("Pumps")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    st.caption("Returns the required duty point (TDH, hydraulic power). Matching an actual "
              "catalogue pump/motor needs a manufacturer curve — not loaded here.")

    with st.form("pump_duty"):
        c1, c2, c3 = st.columns(3)
        flow = c1.number_input("Design flow (L/s)", min_value=0.0, value=5.0)
        static = c2.number_input("Static head (m)", value=20.0)
        eff = c3.number_input("Pump efficiency (0-1)", min_value=0.01, max_value=1.0, value=0.7)
        c4, c5, c6 = st.columns(3)
        friction = c4.number_input("Friction loss (m)", min_value=0.0, value=3.0)
        fitting = c5.number_input("Fitting loss (m)", min_value=0.0, value=1.0)
        equipment = c6.number_input("Equipment loss (m)", min_value=0.0, value=2.0)
        residual = st.number_input("Required residual head (m)", min_value=0.0, value=15.0)
        run = st.form_submit_button("Calculate duty point")
    if run:
        calc_id = next_calc_id(conn, project_id, "pump_duty_selection")
        r = select_pump_duty(flow, static, friction, fitting, equipment, residual, eff, calc_id)
        save_calculation(conn, project_id, r)
        st.markdown(f"### TDH: {r.intermediate['tdh_m']} m — Power: {r.result_value} {r.result_unit}")
        show_result_table(r)


# ------------------------------------------------------------- STORMWATER

def page_stormwater():
    st.header("Stormwater")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    code_id = _project_code(conn, project_id)
    if code_id != "SAUDI_SBC_701":
        st.warning(
            f"Design rainfall intensity data is only loaded for SAUDI_SBC_701 (Riyadh, "
            f"Al-Saleh 1997) — this project's code is {code_id}. Roof-drain and storm-pipe "
            f"sizing will raise MISSING CODE DATA until rainfall data is supplied for this code."
        )
    st.caption("Design rainfall intensity -> Rational Method peak flow -> roof-drain (leader) "
               "sizing -> storm drain pipe sizing. All four steps run on real code/project data "
               "(SBC701 Table 1106 + Ahmed-verified Al-Saleh 1997 Riyadh rainfall depths) — "
               "nothing here is invented or estimated.")

    st.subheader("1. Design rainfall intensity")
    with st.form("rainfall_intensity"):
        c1, c2, c3 = st.columns(3)
        return_period = c1.selectbox("Return period (yr)", [2, 5, 10, 25, 50, 100], index=2)
        duration = c2.selectbox("Design duration", ["15 min", "30 min", "1 hr", "2 hr", "3 hr",
                                                       "4 hr", "6 hr", "8 hr", "12 hr", "24 hr"])
        station = c3.selectbox("Rainfall station", ["riyadh_station_mm", "riyadh_old_airport_mm"])
        run = st.form_submit_button("Calculate intensity")
    if run:
        try:
            calc_id = next_calc_id(conn, project_id, "design_rainfall_intensity")
            r = design_rainfall_intensity(conn, code_id, return_period, duration, calc_id, station=station)
            save_calculation(conn, project_id, r)
            st.session_state["storm_intensity"] = r.result_value
            st.markdown(f"### Design intensity: {r.result_value} {r.result_unit}")
            show_result_table(r)
        except (MissingCodeDataError, ValueError) as e:
            st.error(str(e))

    st.subheader("2. Rational Method peak flow (Q = CIA)")
    intensity_default = st.session_state.get("storm_intensity", 50.0)
    with st.form("rational_method"):
        c1, c2, c3 = st.columns(3)
        runoff_c = c1.number_input("Runoff coefficient C", min_value=0.0, max_value=1.0, value=0.9)
        intensity = c2.number_input("Rainfall intensity (mm/hr)", min_value=0.0, value=float(intensity_default))
        area = c3.number_input("Catchment area (m²)", min_value=0.0, value=500.0)
        run2 = st.form_submit_button("Calculate peak flow")
    if run2:
        calc_id = next_calc_id(conn, project_id, "rational_method_peak_flow")
        r = rational_method_peak_flow(runoff_c, intensity, area, calc_id)
        save_calculation(conn, project_id, r)
        st.session_state["storm_flow_lps"] = r.result_value
        st.markdown(f"### Peak flow: {r.result_value} {r.result_unit}")
        show_result_table(r)

    st.subheader("3. Roof drain (leader) sizing")
    with st.form("roof_drain"):
        c1, c2 = st.columns(2)
        roof_area = c1.number_input("Roof area served (m²)", min_value=0.0, value=500.0)
        rate = c2.number_input("Design rainfall rate (mm/hr)", min_value=0.0, value=float(intensity_default))
        run3 = st.form_submit_button("Size the leader")
    if run3:
        try:
            calc_id = next_calc_id(conn, project_id, "roof_drain_leader_sizing")
            r = size_roof_drain(conn, code_id, roof_area, rate, calc_id)
            save_calculation(conn, project_id, r)
            st.markdown(f"### Leader size: {r.result_value} {r.result_unit}")
            show_result_table(r)
        except (MissingCodeDataError, ValueError) as e:
            st.error(str(e))

    st.subheader("4. Storm drain pipe sizing")
    flow_default = st.session_state.get("storm_flow_lps", 10.0)
    with st.form("storm_pipe"):
        c1, c2, c3 = st.columns(3)
        flow = c1.number_input("Design flow (L/s)", min_value=0.0, value=float(flow_default))
        orientation = c2.selectbox("Orientation", ["vertical", "horizontal"])
        slope = c3.selectbox("Slope (mm/m, horizontal only)", [5, 10, 20, 40])
        run4 = st.form_submit_button("Size the pipe")
    if run4:
        try:
            calc_id = next_calc_id(conn, project_id, "storm_drain_pipe_sizing")
            r = size_storm_drain_pipe(conn, code_id, flow, calc_id, orientation=orientation,
                                       slope_mm_per_m=slope if orientation == "horizontal" else None)
            save_calculation(conn, project_id, r)
            st.markdown(f"### Pipe size: {r.result_value} {r.result_unit}")
            show_result_table(r)
        except (MissingCodeDataError, ValueError) as e:
            st.error(str(e))


# ------------------------------------------------------------- COMPLIANCE

def page_compliance():
    st.header("Code Compliance / QA-QC")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    code_id = _project_code(conn, project_id)
    st.caption(f"Active code: **{code_id}**")

    if st.button("▶ Run full compliance check"):
        results = run_compliance_for_project(conn, project_id, code_id)
        st.session_state["compliance_results"] = results

    results = st.session_state.get("compliance_results")
    if results:
        df = pd.DataFrame(results)
        df["status"] = df["status"].apply(status_badge)
        st.dataframe(df[["rule_id", "severity", "status", "reason", "reference"]], width='stretch')

        n_fail = sum(1 for r in results if r["status"] in ("FAIL",))
        n_warn = sum(1 for r in results if r["status"] in ("WARNING",))
        n_pass = sum(1 for r in results if r["status"] in ("PASS",))
        n_ne = sum(1 for r in results if r["status"] in ("NOT_EVALUATED",))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PASS", n_pass)
        c2.metric("WARNING", n_warn)
        c3.metric("FAIL", n_fail)
        c4.metric("NOT_EVALUATED", n_ne)
    else:
        st.info("Run the compliance check to see results.")


# --------------------------------------------------------- QA/QC DASHBOARD

def page_qaqc_dashboard():
    st.header("QA/QC Dashboard")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return
    st.caption("Project-wide health summary — distinct from the rule-by-rule Code Compliance "
               "page. Answers: is this project's data trustworthy and complete enough to issue? "
               "Re-running replaces this project's previous snapshot (qaqc_results).")

    if st.button("▶ Run QA/QC checks"):
        results = run_qaqc(conn, project_id)
        st.session_state["qaqc_results"] = results

    results = st.session_state.get("qaqc_results")
    if results:
        df = pd.DataFrame(results)
        df_display = df.copy()
        df_display["status"] = df_display["status"].apply(status_badge)
        st.dataframe(df_display[["check_name", "category", "status", "details"]], width='stretch')

        n_fail = sum(1 for r in results if r["status"] == "FAIL")
        n_warn = sum(1 for r in results if r["status"] == "WARNING")
        n_pass = sum(1 for r in results if r["status"] == "PASS")
        n_missing = sum(1 for r in results if r["status"] == "MISSING_DATA")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("PASS", n_pass)
        c2.metric("WARNING", n_warn)
        c3.metric("FAIL", n_fail)
        c4.metric("MISSING_DATA", n_missing)
    else:
        st.info("Run the QA/QC checks to see the project's health summary.")


# ------------------------------------------------------------------ REPORT

def page_report():
    st.header("Report / Export")
    conn = st.session_state.conn
    project_id = _require_project()
    if project_id is None:
        return

    st.caption("The formatted calculation report (spec Section 23) below reads back everything "
               "already calculated, compliance-checked, and QA/QC-summarized for this project — "
               "it never re-computes or re-derives a number.")

    st.subheader("Calculation Report")
    report_md = generate_calculation_report_markdown(conn, project_id)
    st.download_button("Download full report (Markdown)", report_md,
                        file_name=f"project_{project_id}_calculation_report.md")
    with st.expander("Preview report"):
        st.markdown(report_md)

    st.divider()
    st.subheader("Raw data exports (CSV)")

    calcs = conn.execute("SELECT * FROM calculations WHERE project_id=? ORDER BY calc_id", (project_id,)).fetchall()
    if calcs:
        df = pd.DataFrame([dict(c) for c in calcs])
        st.dataframe(df[["calc_id", "calc_type", "result_value", "result_unit", "required_value",
                          "status", "reference"]], width='stretch')
        st.download_button("Download calculations (CSV)", df.to_csv(index=False),
                            file_name=f"project_{project_id}_calculations.csv")
    else:
        st.info("No calculations recorded yet.")

    checks = conn.execute("SELECT * FROM compliance_checks WHERE project_id=? ORDER BY check_id", (project_id,)).fetchall()
    if checks:
        st.subheader("Compliance checks")
        df2 = pd.DataFrame([dict(c) for c in checks])
        st.dataframe(df2[["rule_id", "status", "reason"]], width='stretch')
        st.download_button("Download compliance checks (CSV)", df2.to_csv(index=False),
                            file_name=f"project_{project_id}_compliance.csv")

    qaqc = conn.execute("SELECT * FROM qaqc_results WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
    if qaqc:
        st.subheader("QA/QC results")
        df3 = pd.DataFrame([dict(c) for c in qaqc])
        st.dataframe(df3[["check_name", "category", "status", "details"]], width='stretch')
        st.download_button("Download QA/QC results (CSV)", df3.to_csv(index=False),
                            file_name=f"project_{project_id}_qaqc.csv")


# ---------------------------------------------------------------- helpers

def _require_project():
    project_id = st.session_state.get("project_id")
    if project_id is None:
        st.warning("Create or open a project first (Project page).")
        return None
    return project_id


def _project_code(conn, project_id) -> str:
    row = conn.execute("SELECT code_id FROM projects WHERE project_id=?", (project_id,)).fetchone()
    return row["code_id"]


# -------------------------------------------------------------------- main

def main():
    from app.workbook_page import page_calculation_sheets
    if "conn" not in st.session_state:
        st.session_state.conn = get_conn()
    schema_token=(id(st.session_state.conn),'interactive-packages-1')
    if st.session_state.get('_schema_token')!=schema_token:
        ensure_governance_schema(st.session_state.conn)
        st.session_state['_schema_token']=schema_token

    st.sidebar.title("🔧 Plumbing Design Engine")
    st.sidebar.caption("v0.6.2 — Interactive plumbing calculations")
    st.warning("Review build: calculation benchmarks pass, but code adoption, numeric-table applicability, "
               "model completeness and engineering acceptance still require review.")
    page = st.sidebar.radio("Navigate", [
        "Project", "Code Profiles", "Network Review", "Calculation Sheets", "Design Basis", "Fixtures & Water", "Drainage & Vent",
        "Hot Water", "Tanks", "Pumps", "Stormwater",
        "Code Compliance / QA-QC", "QA/QC Dashboard", "Report / Export",
    ])
    st.sidebar.divider()
    st.sidebar.caption("Phase 7 (Revit/pyRevit integration): scripts are written (bim/pyrevit/) but "
                      "cannot run outside Revit — see docs/ARCHITECTURE.md Section E.")

    pid = st.session_state.get("project_id")
    if pid:
        governance = context(st.session_state.conn, pid)
        token = (pid, governance['fingerprint'])
        if st.session_state.get('_governance_token') != token:
            clear_result_session()
            st.session_state['_governance_token'] = token
        st.sidebar.caption('Engineering review pending' if governance['review_status']=='REVIEW_REQUIRED' else 'Verification complete')
        row = st.session_state.conn.execute(
            "SELECT project_name, code_id FROM projects WHERE project_id=?", (pid,)
        ).fetchone()
        st.sidebar.success(f"Active: #{pid} {row['project_name']} ({row['code_id']})")

    {
        "Project": page_project,
        "Code Profiles": page_code_profiles,
        "Network Review": page_network_review,
        "Calculation Sheets": page_calculation_sheets,
        "Design Basis": page_design_basis,
        "Fixtures & Water": page_water,
        "Drainage & Vent": page_drainage_vent,
        "Hot Water": page_hot_water,
        "Tanks": page_tanks,
        "Pumps": page_pumps,
        "Stormwater": page_stormwater,
        "Code Compliance / QA-QC": page_compliance,
        "QA/QC Dashboard": page_qaqc_dashboard,
        "Report / Export": page_report,
    }[page]()


if __name__ == "__main__":
    main()
