"""
app/db_helpers.py
--------------------
Small glue layer used only by the UI: turns a CalculationResult into a
saved `calculations` row with an auto-generated, human-readable calc_id
(e.g. "CW-003", "DW-001", "V-002"), scoped per project and calc-type
prefix, matching the spec's calc-ID convention (Section 24).
"""

from __future__ import annotations

from models import CalculationResult

CALC_TYPE_PREFIXES = {
    "cold_water_velocity_check": "CW",
    "cold_water_pipe_sizing": "CW",
    "drainage_pipe_sizing": "DW",
    "drainage_min_slope_check": "DW",
    "drainage_velocity_check": "DW",
    "vent_pipe_sizing": "V",
    "hot_water_demand": "HW",
    "hot_water_temperature_check": "HW",
    "hot_water_heater_capacity": "HW",
    "tank_sizing": "TK",
    "pump_duty_selection": "PMP",
    "design_rainfall_intensity": "ST",
    "rational_method_peak_flow": "ST",
    "roof_drain_leader_sizing": "ST",
    "storm_drain_pipe_sizing": "ST",
}


def next_calc_id(conn, project_id: int, calc_type: str) -> str:
    prefix = CALC_TYPE_PREFIXES.get(calc_type, "CALC")
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM calculations
           WHERE project_id = ? AND calc_id LIKE ?""",
        (project_id, f"{prefix}-%"),
    ).fetchone()
    n = (row["n"] or 0) + 1
    return f"{prefix}-{n:03d}"


def save_calculation(conn, project_id: int, result: CalculationResult,
                      target_type: str = None, target_id: str = None) -> None:
    row = result.as_row(project_id, target_type=target_type, target_id=target_id)
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


STATUS_COLOR = {
    "PASS": "🟢",
    "FAIL": "🔴",
    "WARNING": "🟠",
    "ASSUMED": "🟡",
    "MISSING_DATA": "⚪",
    "NOT_EVALUATED": "⚪",
    "CALCULATED_NOT_APPROVED": "🔵",
}


def status_badge(status: str) -> str:
    return f"{STATUS_COLOR.get(status, '⚪')} {status}"
