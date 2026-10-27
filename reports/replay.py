"""Whitelisted reruns from recorded inputs; never executes uploaded Python or expressions."""
import json
import math
from compliance.governance import calculation_is_current
from reports.provenance import engine_manifest, digest


def replay_calculation(conn, project_id, calc_id):
    row = conn.execute('SELECT * FROM calculations WHERE project_id=? AND calc_id=?', (project_id,calc_id)).fetchone()
    if row is None:
        raise ValueError('Calculation does not belong to this project')
    proof = conn.execute('SELECT * FROM calculation_provenance WHERE calc_id=?', (calc_id,)).fetchone()
    if proof is None:
        return dict(status='LEGACY_ENGINE_UNKNOWN', calc_id=calc_id)
    inputs = json.loads(row['inputs_json']); intermediate = json.loads(row['intermediate_json'] or '{}')
    if digest(inputs) != proof['input_sha256']:
        return dict(status='INPUT_CHECKSUM_MISMATCH', calc_id=calc_id)
    if proof['engine_sha256'] != engine_manifest()['source_sha256']:
        return dict(status='ENGINE_CHANGED', calc_id=calc_id)
    if not calculation_is_current(conn, project_id, row):
        return dict(status='STALE_BASIS_OR_SOURCE', calc_id=calc_id)
    def value(name):
        v = inputs[name]
        return v[0] if isinstance(v, (list, tuple)) else v
    kind = row['calc_type']
    if kind == 'hot_water_heater_capacity':
        from calculations.hot_water import heater_capacity
        result = heater_capacity(value('mass_flow_kg_s'), value('cold_water_temp_c'), value('hot_water_temp_c'), 'REPLAY')
    elif kind == 'tank_sizing' and 'avg_daily_demand_lps' in inputs:
        from calculations.tanks import size_domestic_water_tank
        result = size_domestic_water_tank(value('avg_daily_demand_lps'), value('storage_duration_hr'), 'REPLAY', value('freeboard_pct'))
    elif kind == 'pump_duty_selection':
        from calculations.pumps import select_pump_duty
        breakdown = intermediate['tdh_breakdown']
        parts = {key: v[0] for key,v in breakdown.items()}
        result = select_pump_duty(value('design_flow_lps'), efficiency=value('efficiency'), calc_id='REPLAY', **parts)
    elif kind == 'rational_method_peak_flow':
        from calculations.hydraulics import rational_method_peak_flow
        result = rational_method_peak_flow(value('runoff_coefficient'), value('rainfall_intensity_mm_hr'), value('catchment_area_m2'), 'REPLAY')
    elif kind == 'hot_water_demand' and 'fixture_schedule' in inputs:
        from calculations.hot_water import hot_water_demand
        result = hot_water_demand(conn, inputs['fixture_schedule'], 'REPLAY', value('demand_factor'), value('storage_capacity_factor'))
    else:
        return dict(status='REPLAY_NOT_SUPPORTED', calc_id=calc_id,
                    detail='Inputs and intermediate evidence remain available in the review packet; no rerun is claimed.')
    fields = ('result_value', 'required_value', 'selected_value')
    actual = {field: getattr(result,field) for field in fields}
    expected = {field: row[field] for field in fields}
    matches = all(actual[f] is expected[f] if actual[f] is None or expected[f] is None else
                  math.isclose(actual[f], expected[f], rel_tol=1e-9, abs_tol=1e-6) for f in fields)
    return dict(status='MATCH' if matches else 'MISMATCH', calc_id=calc_id, expected=expected, actual=actual,
                result_unit=result.result_unit, notes='Numerical reproduction is not code or engineering approval.')
