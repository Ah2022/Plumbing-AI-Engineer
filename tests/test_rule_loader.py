"""
tests/test_rule_loader.py
----------------------------
Regression tests for the code-rule ETL. Run with: pytest tests/
"""

from database.db import init_db
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import sync_predicate_flags, RULE_PREDICATES
from calculations.hydraulics import velocity_from_flow, hazen_williams_head_loss, rational_method_peak_flow


def _fresh_conn(tmp_path):
    return init_db(db_path=tmp_path / "test.db", reset=True)


def test_all_four_codes_load(tmp_path):
    conn = _fresh_conn(tmp_path)
    summary = load_all_rules(conn)
    assert set(summary.keys()) == {"IPC", "UPC", "EGYPT_LOCAL", "SAUDI_SBC_701"}
    assert sum(summary.values()) == 32  # matches the supplied dataset exactly


def test_ipc_w_002_parameter_preserved(tmp_path):
    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    row = conn.execute("SELECT parameters_json FROM code_rules WHERE rule_id='IPC-W-002'").fetchone()
    assert row is not None
    assert "80" in row["parameters_json"]


def test_predicate_flags_sync(tmp_path):
    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    n = sync_predicate_flags(conn)
    assert n == len(RULE_PREDICATES)
    total = conn.execute("SELECT COUNT(*) FROM code_rules").fetchone()[0]
    with_predicate = conn.execute("SELECT COUNT(*) FROM code_rules WHERE has_predicate=1").fetchone()[0]
    assert with_predicate == n
    assert with_predicate < total  # most rules still correctly require BIM topology / manual review


def test_velocity_from_flow_known_value():
    # Q=1 L/s through a 25mm ID pipe: A = pi*0.025^2/4 = 4.9087e-4 m2, V = 0.001/4.9087e-4 = 2.0372 m/s
    r = velocity_from_flow(flow_lps=1.0, internal_diameter_mm=25.0, calc_id="T-001")
    assert abs(r.result_value - 2.0372) < 0.001


def test_hazen_williams_positive_and_traceable():
    r = hazen_williams_head_loss(flow_lps=2.5, internal_diameter_mm=50.0, length_m=40.0, c_factor=150, calc_id="T-002")
    assert r.result_value > 0
    assert "10.67" in r.formula
    assert r.inputs["c_factor"] == (150, "-")


def test_rational_method_zero_area_gives_zero_flow():
    r = rational_method_peak_flow(runoff_coefficient=0.9, rainfall_intensity_mm_hr=100, catchment_area_m2=0, calc_id="T-003")
    assert r.result_value == 0


def test_ipc_velocity_limit_real_data(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from calculations.water import check_velocity_limit

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    conn.execute(
        "INSERT INTO projects (project_id, project_name, building_type) VALUES (1, 'T', 'Hospital')"
    )
    r = check_velocity_limit(conn, 1, "IPC", "P-1", flow_lps=1.0, internal_diameter_mm=25.0, calc_id="T-V1")
    assert r.required_value == 1.8
    assert r.status == "FAIL"  # 2.037 m/s > 1.8 m/s limit — a real, correct engineering result


def test_sbc701_velocity_limit_gap_without_fallback(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from calculations.water import check_velocity_limit
    from models import MissingCodeDataError

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    conn.execute(
        "INSERT INTO projects (project_id, project_name, building_type) VALUES (1, 'T', 'Hospital')"
    )
    try:
        check_velocity_limit(conn, 1, "SAUDI_SBC_701", "P-1", flow_lps=1.0, internal_diameter_mm=25.0, calc_id="T-V2")
        assert False, "should have raised MissingCodeDataError"
    except MissingCodeDataError:
        pass


def test_egypt_velocity_limit_matches_real_phrasing_with_max_general(tmp_path):
    """
    EGYPT_LOCAL's own velocity limit is real data ("Maximum water velocity
    in distribution piping" = 2.4 m/s) but is phrased differently from the
    other codes' "recommended design velocity" wording that the default
    kind matches. This is real code text, not a gap -- kind='max_general'
    must find it rather than raising MissingCodeDataError.
    """
    from database.load_design_tables import load_all_workbooks
    from calculations.water import check_velocity_limit

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    conn.execute(
        "INSERT INTO projects (project_id, project_name, building_type) VALUES (1, 'T', 'Hotel')"
    )
    r = check_velocity_limit(conn, 1, "EGYPT_LOCAL", "P-1", flow_lps=2.0, internal_diameter_mm=50.0,
                              calc_id="T-V3", velocity_kind="max_general")
    assert r.required_value == 2.4
    assert r.status == "PASS"


def test_sbc701_velocity_limit_explicit_fallback_is_flagged(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from calculations.water import check_velocity_limit

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    conn.execute(
        "INSERT INTO projects (project_id, project_name, building_type) VALUES (1, 'T', 'Hospital')"
    )
    r = check_velocity_limit(conn, 1, "SAUDI_SBC_701", "P-1", flow_lps=1.0, internal_diameter_mm=25.0,
                              calc_id="T-V3", allow_fallback_code="IPC")
    assert "fallback from IPC" in r.reference
    assert "borrowed from IPC" in r.notes


def test_ipc_fixture_units_real_data(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from calculations.water import total_fixture_units

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    fixtures = [{"fixture_name": "Water closet", "occupancy": "Public", "control": "Flushometer", "quantity": 40}]
    result = total_fixture_units(conn, "IPC", fixtures)
    assert result["total_cold_fu"] > 0


def test_riyadh_rainfall_depth_confirmed(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from database.load_confirmed_additions import load_all_confirmed_additions
    from database.design_table_api import get_table_records

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    load_all_confirmed_additions(conn)

    recs = get_table_records(conn, "SAUDI_SBC_701", "storm", "Riyadh 24hr Design Rainfall Depth")
    match = [r for r in recs if r.get("return_period_yr", (None,))[0] == 25]
    assert len(match) == 1
    assert match[0]["riyadh_station_mm"][0] == 34.8
    assert match[0]["riyadh_old_airport_mm"][0] == 43.8


def test_ppr_pn16_velocity_manufacturer_data(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from database.load_confirmed_additions import load_all_confirmed_additions
    from calculations.water import check_velocity_limit

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)
    load_all_confirmed_additions(conn)
    conn.execute("INSERT INTO projects (project_id, project_name, building_type) VALUES (1,'T','Hospital')")

    r = check_velocity_limit(conn, 1, "SAUDI_SBC_701", "P-1", flow_lps=1.0, internal_diameter_mm=25.0,
                              calc_id="T-V4", material="PPR")
    assert r.required_value == 3.05
    assert r.status == "PASS"


def test_hospital_fixture_alias_resolves_to_water_closet(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from calculations.water import total_fixture_units

    conn = _fresh_conn(tmp_path)
    load_all_rules(conn)
    load_all_workbooks(conn)

    aliased = total_fixture_units(conn, "IPC", [
        {"fixture_name": "Clinical sink", "occupancy": "Public", "control": "Flushometer", "quantity": 5}
    ])
    direct_wc = total_fixture_units(conn, "IPC", [
        {"fixture_name": "Water closet", "occupancy": "Public", "control": "Flushometer", "quantity": 5}
    ])
    assert aliased["total_cold_fu"] == direct_wc["total_cold_fu"]


def _conn_with_all_data(tmp_path):
    conn = _fresh_conn(tmp_path)
    from database.load_design_tables import load_all_workbooks
    from database.load_confirmed_additions import load_all_confirmed_additions
    load_all_rules(conn)
    load_all_workbooks(conn)
    load_all_confirmed_additions(conn)
    return conn


def test_sbc701_drainage_sizing_known_values(tmp_path):
    from calculations.drainage import size_drainage_pipe
    conn = _conn_with_all_data(tmp_path)
    r6 = size_drainage_pipe(conn, "SAUDI_SBC_701", total_dfu=6, context="horizontal_branch", calc_id="T-D1")
    assert r6.result_value == 50.0
    r7 = size_drainage_pipe(conn, "SAUDI_SBC_701", total_dfu=7, context="horizontal_branch", calc_id="T-D2")
    assert r7.result_value == 65.0


def test_sbc701_min_slope_pass_and_fail(tmp_path):
    from calculations.drainage import check_min_slope
    conn = _conn_with_all_data(tmp_path)
    ok = check_min_slope(conn, "SAUDI_SBC_701", pipe_size_mm=100, selected_slope_pct=1.0, calc_id="T-S1")
    assert ok.status == "PASS"
    bad = check_min_slope(conn, "SAUDI_SBC_701", pipe_size_mm=100, selected_slope_pct=0.5, calc_id="T-S2")
    assert bad.status == "FAIL"


def test_sbc701_vent_sizing_known_value(tmp_path):
    from calculations.vent import size_vent_pipe
    conn = _conn_with_all_data(tmp_path)
    r = size_vent_pipe(conn, "SAUDI_SBC_701", total_dfu=4, calc_id="T-V5")
    assert r.result_value == 50.0


def test_ipc_vent_multidim_known_value(tmp_path):
    from calculations.vent import size_vent_pipe_multidim
    conn = _conn_with_all_data(tmp_path)
    r = size_vent_pipe_multidim(conn, "IPC", stack_size_in=4.0, total_fu=200, developed_length_ft=90, calc_id="T-V6")
    assert r.result_value == 2.5
    assert r.result_unit == "in"


def test_ipc_vent_simple_lookup_correctly_refuses(tmp_path):
    """IPC has no simple 1D vent table -- must raise, never silently misread inches as mm."""
    from calculations.vent import size_vent_pipe
    from models import MissingCodeDataError
    conn = _conn_with_all_data(tmp_path)
    try:
        size_vent_pipe(conn, "IPC", total_dfu=50, calc_id="T-V7")
        assert False, "should have raised MissingCodeDataError"
    except MissingCodeDataError:
        pass


def test_sbc701_pipe_sizing_from_demand_known_value(tmp_path):
    from calculations.water import size_pipe_from_demand
    conn = _conn_with_all_data(tmp_path)
    r = size_pipe_from_demand(conn, "SAUDI_SBC_701", total_wsfu=12, calc_id="T-CW1",
                               control_type="flush_tank", material="PPR")
    assert r.intermediate["demand_lpm"] == 60.0
    assert abs(r.result_value - 20.43) < 0.05


def test_sbc701_pipe_sizing_interpolates_between_real_points(tmp_path):
    from calculations.water import size_pipe_from_demand
    conn = _conn_with_all_data(tmp_path)
    r = size_pipe_from_demand(conn, "SAUDI_SBC_701", total_wsfu=12.5, calc_id="T-CW2",
                               control_type="flush_tank", material="PPR")
    assert r.intermediate["demand_lpm"] == 61.0  # midpoint of 60 and 62


def test_sbc701_pipe_sizing_beyond_table_range_raises(tmp_path):
    from calculations.water import size_pipe_from_demand
    from models import MissingCodeDataError
    conn = _conn_with_all_data(tmp_path)
    try:
        size_pipe_from_demand(conn, "SAUDI_SBC_701", total_wsfu=999999, calc_id="T-CW3", material="PPR")
        assert False, "should have raised -- beyond table range, no extrapolation"
    except MissingCodeDataError:
        pass


def test_sbc701_pipe_sizing_respects_fixture_minimum_floor(tmp_path):
    from calculations.water import size_pipe_from_demand
    conn = _conn_with_all_data(tmp_path)
    r = size_pipe_from_demand(conn, "SAUDI_SBC_701", total_wsfu=12, calc_id="T-CW4",
                               control_type="flush_valve", material="PPR",
                               fixture_min_size_context="Water closet, flushometer valve")
    assert r.intermediate["fixture_min_nominal_mm"] == 25.0
    assert r.selected_value is None  # no catalogue: nominal minimum is not an invented internal diameter


def test_hot_water_demand_known_value(tmp_path):
    from calculations.hot_water import hot_water_demand
    conn = _conn_with_all_data(tmp_path)
    fixtures = [{"fixture_name": "Showers", "quantity": 20}, {"fixture_name": "Basins, private lavatory", "quantity": 40}]
    r = hot_water_demand(conn, fixtures, calc_id="T-HW1")
    assert r.intermediate["total_connected_demand_gph"] == 1580.0
    assert r.result_value == 395.0  # 1580 * 0.25


def test_hot_water_scald_protection_pass_and_fail(tmp_path):
    from calculations.hot_water import check_hot_water_temperature
    conn = _conn_with_all_data(tmp_path)
    ok = check_hot_water_temperature(conn, "scald_protection_patient_areas", 46.1, calc_id="T-HW2")
    assert ok.status == "PASS"
    bad = check_hot_water_temperature(conn, "scald_protection_patient_areas", 50.0, calc_id="T-HW3")
    assert bad.status == "FAIL"


def test_hot_water_legionella_storage_minimum(tmp_path):
    from calculations.hot_water import check_hot_water_temperature
    conn = _conn_with_all_data(tmp_path)
    r = check_hot_water_temperature(conn, "legionella_storage_minimum", 55.0, calc_id="T-HW4")
    assert r.status == "FAIL"
    assert r.required_value == 60.0


def test_heater_capacity_known_value(tmp_path):
    from calculations.hot_water import heater_capacity
    r = heater_capacity(mass_flow_kg_s=0.5, cold_water_temp_c=15, hot_water_temp_c=60, calc_id="T-HW5")
    assert abs(r.result_value - 94.185) < 0.01


def test_domestic_tank_sizing_known_value():
    from calculations.tanks import size_domestic_water_tank
    r = size_domestic_water_tank(avg_daily_demand_lps=5.0, storage_duration_hr=4.0, calc_id="T-TK1")
    assert r.required_value == 72.0
    assert r.selected_value == 79.2


def test_hot_water_tank_derived_from_demand(tmp_path):
    from calculations.hot_water import hot_water_demand
    from calculations.tanks import size_hot_water_storage_tank_from_demand
    conn = _conn_with_all_data(tmp_path)
    fixtures = [{"fixture_name": "Showers", "quantity": 20}, {"fixture_name": "Basins, private lavatory", "quantity": 40}]
    hw = hot_water_demand(conn, fixtures, calc_id="T-HW6")
    tk = size_hot_water_storage_tank_from_demand(hw, calc_id="T-TK2")
    assert abs(tk.result_value - 897.1) < 0.1


def test_pump_duty_known_value():
    from calculations.pumps import select_pump_duty
    r = select_pump_duty(design_flow_lps=5.0, static_head_m=20, friction_loss_m=3, fitting_loss_m=1,
                          equipment_loss_m=2, required_residual_head_m=15, efficiency=0.7, calc_id="T-PMP1")
    assert r.intermediate["tdh_m"] == 41
    assert abs(r.result_value - 2.8719) < 0.001


def test_list_water_fixture_unit_choices_sbc701(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from database.design_table_api import list_water_fixture_unit_choices

    conn = _fresh_conn(tmp_path)
    load_all_workbooks(conn)
    choices = list_water_fixture_unit_choices(conn, "SAUDI_SBC_701")
    assert len(choices) > 0
    assert all(c["wsfu_value"] is not None for c in choices)
    assert any("Bathroom group" in c["fixture_name"] for c in choices)


def test_list_water_fixture_unit_choices_upc_splits_by_occupancy(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from database.design_table_api import list_water_fixture_unit_choices

    conn = _fresh_conn(tmp_path)
    load_all_workbooks(conn)
    choices = list_water_fixture_unit_choices(conn, "UPC")
    assert len(choices) > 0
    assert all(c["occupancy"] in ("Private", "Public", "Assembly") for c in choices)


def test_list_water_fixture_unit_choices_ipc_has_real_wsfu_table_too(tmp_path):
    """IPC's '1_Fixture_Units' tab actually contains TWO sub-tables: a
    drainage-FU one (dfu_ipc/dfu_upc) and a separate genuine WSFU one
    (fixture+occupancy+control+cold+hot+total) -- get_table_records merges
    both, and this function must pick out only the WSFU-shaped rows."""
    from database.load_design_tables import load_all_workbooks
    from database.design_table_api import list_water_fixture_unit_choices

    conn = _fresh_conn(tmp_path)
    load_all_workbooks(conn)
    choices = list_water_fixture_unit_choices(conn, "IPC")
    assert len(choices) > 0
    assert all(c["wsfu_value"] is not None for c in choices)
    assert any(c["fixture_name"] == "Water closet" for c in choices)


def test_list_water_fixture_unit_choices_empty_for_egypt(tmp_path):
    """Egypt has no '1_Fixture_Units' table loaded at all -> [], not a guess."""
    from database.load_design_tables import load_all_workbooks
    from database.design_table_api import list_water_fixture_unit_choices

    conn = _fresh_conn(tmp_path)
    load_all_workbooks(conn)
    assert list_water_fixture_unit_choices(conn, "EGYPT_LOCAL") == []


def test_total_fixture_units_uses_preselected_wsfu_value_directly(tmp_path):
    """A fixture picked from the dropdown carries its own wsfu_value --
    total_fixture_units must use it directly, without re-doing the
    free-text table lookup (which would fail for codes like IPC anyway)."""
    from database.load_design_tables import load_all_workbooks
    from calculations.water import total_fixture_units

    conn = _fresh_conn(tmp_path)
    load_all_workbooks(conn)
    fixtures = [{"fixture_name": "Some Fixture", "quantity": 3, "wsfu_value": 2.0, "confidence": "CONFIRMED"}]
    result = total_fixture_units(conn, "IPC", fixtures)  # IPC has no WSFU table at all
    assert result["total_cold_fu"] == 6.0
    assert result["confidence"] == "CONFIRMED"


def test_total_fixture_units_flags_manual_entry_confidence(tmp_path):
    from database.load_design_tables import load_all_workbooks
    from calculations.water import total_fixture_units

    conn = _fresh_conn(tmp_path)
    load_all_workbooks(conn)
    fixtures = [{"fixture_name": "Manually entered", "quantity": 2, "wsfu_value": 1.5, "confidence": "FLAGGED"}]
    result = total_fixture_units(conn, "EGYPT_LOCAL", fixtures)
    assert result["total_cold_fu"] == 3.0
    assert result["confidence"] == "FLAGGED"
