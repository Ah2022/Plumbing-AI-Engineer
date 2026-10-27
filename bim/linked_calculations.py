"""Attribute an existing current equipment calculation without rewriting its original record."""
import json
from app.db_helpers import next_calc_id, save_calculation
from compliance.governance import calculation_is_current
from models import CalculationResult


def link_equipment_calculation(conn, project_id, model_key, target_type, target_id, calc_id, reviewer, evidence):
    if target_type not in ('tank','pump') or not reviewer.strip() or not evidence.strip():
        raise ValueError('Select tank/pump and provide reviewer and linking evidence')
    table, key = ('tanks','tank_id') if target_type=='tank' else ('pumps','pump_id')
    target = conn.execute(f'SELECT * FROM {table} WHERE project_id=? AND revit_model_key=? AND {key}=?',
                          (project_id,model_key,target_id)).fetchone()
    source = conn.execute('SELECT * FROM calculations WHERE project_id=? AND calc_id=?',(project_id,calc_id)).fetchone()
    expected = 'tank_sizing' if target_type=='tank' else 'pump_duty_selection'
    if target is None or source is None or source['calc_type']!=expected or not calculation_is_current(conn,project_id,source):
        raise ValueError('Equipment target or current matching calculation is unavailable')
    if conn.execute('SELECT 1 FROM calculation_overrides WHERE project_id=? AND calc_id=?',(project_id,calc_id)).fetchone():
        raise ValueError('Resolve/recalculate the override proposal before attributing this calculation')
    inputs = json.loads(source['inputs_json'])
    inputs.update(source_calc_id=calc_id, linking_reviewer=reviewer, linking_evidence=evidence)
    result = CalculationResult(next_calc_id(conn,project_id,expected),expected,source['formula'],inputs,
        json.loads(source['intermediate_json'] or '{}'),source['result_value'],source['result_unit'],
        required_value=source['required_value'],selected_value=source['selected_value'],status=source['status'],
        reference=source['reference'],notes=f'Attributed from {calc_id}; reviewer {reviewer}; {evidence}. Original retained.')
    save_calculation(conn,project_id,result,target_type=target_type,target_id=target_id)
    return result.calc_id
