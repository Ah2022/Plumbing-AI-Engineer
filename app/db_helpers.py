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
    'engineering_module':'EM',
    'general_network_check':'NG',
    "model_design_check":"MD",
    "model_document_review":"MR",
    "reference_workbook_scenario":"WB",
    "water_network_check":"NW",
    "drainage_network_check":"ND",
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
    from uuid import uuid4
    prefix = CALC_TYPE_PREFIXES.get(calc_type, "CALC")
    return f"{prefix}-P{project_id}-{uuid4().hex}"


def save_calculation(conn, project_id: int, result: CalculationResult,
                      target_type: str = None, target_id: str = None) -> None:
    row = result.as_row(project_id, target_type=target_type, target_id=target_id)
    import json
    from compliance.governance import context
    from database.review_schema import ensure_review_schema
    from reports.provenance import engine_manifest, digest
    ensure_review_schema(conn)
    manifest = engine_manifest()
    governance = context(conn, project_id)
    # Pilot adapter/coverage acceptance is independent of the project's code adoption.
    review_status = 'REVIEW_REQUIRED' if result.calc_type in ('model_design_check', 'model_document_review', 'general_network_check', 'engineering_module') else governance['review_status']
    row.update(notes=result.notes, governance_json=json.dumps(governance, sort_keys=True),
               review_status=review_status)
    result.review_status = review_status
    with conn:
        if target_type is not None and target_id is not None:
            conn.execute('UPDATE calculations SET is_current=0 WHERE project_id=? AND calc_type=? AND target_type=? AND target_id=?',
                         (project_id,result.calc_type,target_type,str(target_id)))
        conn.execute(
            """INSERT INTO calculations (calc_id, project_id, calc_type, target_type, target_id,
                 formula, inputs_json, intermediate_json, result_value, result_unit,
                 required_value, selected_value, status, code_rule_id, reference,
                 notes,governance_json,review_status,is_current)
               VALUES (:calc_id,:project_id,:calc_type,:target_type,:target_id,:formula,
                 :inputs_json,:intermediate_json,:result_value,:result_unit,
                 :required_value,:selected_value,:status,:code_rule_id,:reference,
                 :notes,:governance_json,:review_status,1)""",
            row,
        )
        conn.execute('''INSERT INTO calculation_provenance(calc_id,input_sha256,engine_sha256,manifest_json)
                        VALUES (?,?,?,?)''',
                     (result.calc_id, digest(result.inputs), manifest['source_sha256'], json.dumps(manifest)))



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
