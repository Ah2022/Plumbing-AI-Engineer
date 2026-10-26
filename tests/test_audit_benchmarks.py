"""Independent Phase 1 checks; strict xfails reproduce open audit findings.

These cases use synthetic inputs and dimensional identities, not licensed tables.
An xfail is a known defect, not engineering acceptance. Remove its marker when fixed.
"""
import math

import pytest

from app.db_helpers import next_calc_id, save_calculation
from bim.exchange import import_revit_extract
from bim.schemas import empty_extract_payload
from calculations.hydraulics import (
    velocity_from_flow, darcy_weisbach_head_loss, hazen_williams_head_loss,
    total_dynamic_head, pump_power, rational_method_peak_flow, q_heat,
)
from calculations.tanks import size_domestic_water_tank
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import (
    check_static_pressure_threshold, check_water_sizing_justified,
)
from database.db import init_db
from models import CalculationResult


@pytest.fixture
def projects(tmp_path):
    conn = init_db(tmp_path / "audit.db")
    load_all_rules(conn)
    for pid in (1, 2):
        conn.execute("INSERT INTO projects (project_id, project_name, building_type, code_id) "
                     "VALUES (?, ?, 'Office', 'IPC')", (pid, f"Synthetic {pid}"))
    conn.commit()
    yield conn
    conn.close()


def test_continuity_one_litre_per_second():
    expected = 0.001 / (math.pi * 0.025 ** 2 / 4)
    assert velocity_from_flow(1, 25, "A-1").result_value == pytest.approx(expected, abs=0.00005)


def test_darcy_against_independent_velocity():
    velocity = 0.0025 / (math.pi * 0.05 ** 2 / 4)
    expected = 0.02 * (40 / 0.05) * velocity ** 2 / (2 * 9.80665)
    assert darcy_weisbach_head_loss(2.5, 50, 40, 0.02, "A-2").result_value == pytest.approx(expected, abs=0.0001)


def test_hazen_williams_independent_evaluation():
    expected = 10.67 * 40 * (0.0025 / 150) ** 1.852 / 0.05 ** 4.8704
    assert hazen_williams_head_loss(2.5, 50, 40, 150, "A-3").result_value == pytest.approx(expected, abs=0.00005)


def test_head_balance():
    assert total_dynamic_head(20, 3, 1, 2, 15, "A-4").result_value == 41


def test_pump_input_power_energy_balance():
    expected_kw = 1000 * 9.80665 * 0.005 * 41 / 0.7 / 1000
    assert pump_power(5, 41, 0.7, "A-5").result_value == pytest.approx(expected_kw, abs=0.00005)


def test_heating_energy_balance():
    assert q_heat(0.5, 4.186, 45, "A-6").result_value == pytest.approx(94.185)


def test_storage_volume_unit_conversion():
    result = size_domestic_water_tank(5, 4, "A-7")
    assert result.required_value == 72
    assert result.selected_value == pytest.approx(79.2)


def test_rain_depth_volume_identity():
    # 3600 mm/hr on 1 m2 = 3600 litres/hour = exactly 1 litre/second.
    assert rational_method_peak_flow(1, 3600, 1, "A-8").result_value == 1


def test_zero_diameter_rejected():
    with pytest.raises(ValueError):
        velocity_from_flow(1, 0, "A-9")


def test_impossible_efficiency_rejected():
    with pytest.raises(ValueError):
        pump_power(5, 41, 1.1, "A-10")


def test_nonfinite_flow_rejected():
    with pytest.raises(ValueError):
        velocity_from_flow(float("nan"), 25, "A-11")


def test_pending_pressure_not_passed(projects):
    projects.execute("INSERT INTO design_basis_items "
                     "(project_id,item_key,item_value,status) VALUES (1,'static_pressure_psi','60','PENDING')")
    rule = projects.execute("SELECT * FROM code_rules WHERE rule_id='IPC-W-002'").fetchone()
    assert check_static_pressure_threshold(projects, 1, rule).status != "PASS"


def test_rejected_prv_not_passed(projects):
    projects.execute("INSERT INTO design_basis_items "
                     "(project_id,item_key,item_value,status) VALUES (1,'static_pressure_psi','100','APPROVED')")
    projects.execute("INSERT INTO design_basis_items "
                     "(project_id,item_key,item_value,status) VALUES (1,'pressure_reducing_valve_provided','yes','REJECTED')")
    rule = projects.execute("SELECT * FROM code_rules WHERE rule_id='IPC-W-002'").fetchone()
    assert check_static_pressure_threshold(projects, 1, rule).status != "PASS"


def test_failed_sizing_not_passed(projects):
    result = CalculationResult("CW-001", "cold_water_pipe_sizing", "synthetic", {}, {}, 1, "mm", status="FAIL")
    save_calculation(projects, 1, result)
    assert check_water_sizing_justified(projects, 1, None).status != "PASS"


def test_calculation_ids_work_across_projects(projects):
    for pid in (1, 2):
        cid = next_calc_id(projects, pid, "cold_water_pipe_sizing")
        result = CalculationResult(cid, "cold_water_pipe_sizing", "synthetic", {}, {}, 1, "mm")
        save_calculation(projects, pid, result)
    assert projects.execute("SELECT COUNT(*) FROM calculations").fetchone()[0] == 2


def test_calculation_notes_survive_save(projects):
    result = CalculationResult("A-12", "synthetic", "synthetic", {}, {}, 1, "mm", notes="Synthetic review note")
    save_calculation(projects, 1, result)
    row = dict(projects.execute("SELECT * FROM calculations WHERE calc_id='A-12'").fetchone())
    assert row.get("notes") == result.notes


def test_revit_ids_are_scoped_to_project(projects):
    payload = empty_extract_payload("Synthetic.rvt", "2026-10-26T00:00:00")
    payload["pipes"] = [{"revit_element_id": "123", "system": "cold_water",
                          "length_m": 10, "nominal_diameter_mm": 25}]
    import_revit_extract(projects, 1, payload)
    import_revit_extract(projects, 2, payload)
    assert projects.execute("SELECT COUNT(*) FROM pipes WHERE project_id=2").fetchone()[0] == 1


def test_revit_reimport_updates_flow_and_connectivity(projects):
    payload = empty_extract_payload("Synthetic.rvt", "2026-10-26T00:00:00")
    pipe = {"revit_element_id": "123", "system": "cold_water", "length_m": 10,
            "nominal_diameter_mm": 25, "flow_lps": 1, "from_node": "A", "to_node": "B"}
    payload["pipes"] = [pipe]
    import_revit_extract(projects, 1, payload)
    pipe.update(flow_lps=2, to_node="C")
    import_revit_extract(projects, 1, payload)
    row = projects.execute("SELECT flow_lps,to_node FROM pipes WHERE project_id=1").fetchone()
    assert (row["flow_lps"], row["to_node"]) == (2, "C")
