"""Physical boundaries, table boundaries and model persistence independence."""
import json
import math
from pathlib import Path
import sqlite3

import pytest

from app.db_helpers import next_calc_id,save_calculation
from bim.exchange import import_revit_extract,export_results_for_revit,InvalidExtractPayload
from bim.schemas import empty_extract_payload,validate_extract_payload
from calculations.hydraulics import (
    velocity_from_flow,darcy_weisbach_head_loss,hazen_williams_head_loss,pump_power,
    rational_method_peak_flow,q_heat,
)
from compliance.rule_loader import load_all_rules
from compliance.rule_registry import check_static_pressure_threshold
from database.db import init_db
from database.design_table_api import get_demand_from_wsfu
from models import CalculationResult
from units.convert import inch_to_mm,mm_to_inch,psi_to_kpa,kpa_to_psi,f_to_c,c_to_f


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-float('inf'),True,'1',None])
def test_invalid_numeric_input_has_actionable_error(bad):
    with pytest.raises(ValueError):velocity_from_flow(bad,25,'T')


@pytest.mark.parametrize('call',[
    lambda:velocity_from_flow(-1,25,'T'),lambda:velocity_from_flow(1,-25,'T'),
    lambda:darcy_weisbach_head_loss(1,25,10,0,'T'),
    lambda:hazen_williams_head_loss(1,25,-10,100,'T'),
    lambda:hazen_williams_head_loss('invalid',25,10,100,'T'),
    lambda:pump_power(1,10,0,'T'),lambda:pump_power(1,10,1.01,'T'),
    lambda:rational_method_peak_flow(1.1,100,1,'T'),
    lambda:rational_method_peak_flow(.5,-100,1,'T'),
    lambda:q_heat(.5,4.186,-10,'T'),
])
def test_physical_domains_reject_impossible_values(call):
    with pytest.raises(ValueError):call()


def test_zero_flow_is_valid():
    assert velocity_from_flow(0,25,'T').result_value==0
    assert rational_method_peak_flow(0,100,10,'T').result_value==0


def test_darcy_uses_unrounded_intermediate_velocity():
    r=darcy_weisbach_head_loss(.000001,1000,1,.02,'T')
    expected=1e-9/(math.pi/4)
    assert r.intermediate['velocity_m_s']==pytest.approx(expected,rel=1e-12)
    assert r.intermediate['velocity_m_s']>0


def test_efficiency_adjusted_power_distinguished_from_hydraulic_power():
    r=pump_power(1,10,.5,'T')
    assert r.intermediate['hydraulic_power_kw']==pytest.approx(.0980665)
    assert r.intermediate['efficiency_adjusted_power_kw']==pytest.approx(.196133)


def test_rainfall_volume_identity_multiple_units():
    # 100 mm/hour x 36 m2 = 3600 litres/hour, exactly 1 L/s.
    assert rational_method_peak_flow(1,100,36,'T').result_value==1
    assert rational_method_peak_flow(.5,100,36,'T').result_value==.5


def test_explicit_unit_roundtrips():
    assert mm_to_inch(inch_to_mm(2))==pytest.approx(2)
    assert kpa_to_psi(psi_to_kpa(40))==pytest.approx(40)
    assert c_to_f(f_to_c(212))==pytest.approx(212)


def test_conversion_rejects_nonfinite():
    with pytest.raises(ValueError):inch_to_mm(float('nan'))


def test_result_contract_rejects_nonfinite_trace():
    with pytest.raises(ValueError):CalculationResult('T','test','x',{}, {},float('inf'),'m')
    with pytest.raises(ValueError):CalculationResult('T','test','x',{'x':(float('nan'),'m')},{},1,'m')


@pytest.fixture
def db(tmp_path):
    conn=init_db(tmp_path/'foundations.db');load_all_rules(conn)
    for pid in (1,2):
        conn.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES (?,?,'Office','IPC')",(pid,'Synthetic'))
    conn.commit();yield conn;conn.close()


def test_calculation_identity_does_not_reuse_after_deletion(db):
    first=next_calc_id(db,1,'cold_water_pipe_sizing')
    save_calculation(db,1,CalculationResult(first,'cold_water_pipe_sizing','x',{}, {},1,'mm'))
    db.execute('DELETE FROM calculations WHERE calc_id=?',(first,));db.commit()
    assert next_calc_id(db,1,'cold_water_pipe_sizing')!=first


def test_failed_save_does_not_invalidate_current_target(db):
    old=velocity_from_flow(1,25,'DUPLICATE')
    save_calculation(db,1,old,target_type='pipe',target_id='P')
    with pytest.raises(sqlite3.IntegrityError):save_calculation(db,1,old,target_type='pipe',target_id='P')
    assert db.execute("SELECT is_current FROM calculations WHERE calc_id='DUPLICATE'").fetchone()[0]==1


def test_new_target_calculation_retains_history_as_stale(db):
    for cid in ('OLD','NEW'):save_calculation(db,1,velocity_from_flow(1,25,cid),target_type='pipe',target_id='P')
    rows=dict(db.execute('SELECT calc_id,is_current FROM calculations').fetchall())
    assert rows=={'OLD':0,'NEW':1}


def test_latest_rejected_pressure_supersedes_old_approval(db):
    for value,status in [('60','APPROVED'),('60','REJECTED')]:
        db.execute("INSERT INTO design_basis_items(project_id,item_key,item_value,status) VALUES (1,'static_pressure_psi',?,?)",(value,status))
    rule=db.execute("SELECT * FROM code_rules WHERE rule_id='IPC-W-002'").fetchone()
    assert check_static_pressure_threshold(db,1,rule).status=='NOT_EVALUATED'


def test_pressure_key_and_units_cannot_disagree(db):
    db.execute("INSERT INTO design_basis_items(project_id,item_key,item_value,status,unit) VALUES (1,'static_pressure_psi','60','APPROVED','kPa')")
    rule=db.execute("SELECT * FROM code_rules WHERE rule_id='IPC-W-002'").fetchone()
    assert check_static_pressure_threshold(db,1,rule).status=='NOT_EVALUATED'


def demand_table(db):
    cur=db.execute("INSERT INTO design_tables(code_id,domain,table_name,reference,status) VALUES ('IPC','water','2_Demand_Conversion','SYNTHETIC_TEST_ONLY','POPULATED')")
    for row,w,q in [('a',10,30),('b',20,60)]:
        for key,value in [('wsfu',w),('flush_tank_lpm',q)]:
            db.execute('INSERT INTO design_table_values(table_id,row_key,col_key,value_num) VALUES (?,?,?,?)',(cur.lastrowid,row,key,value))
    db.commit();return cur.lastrowid


def test_demand_exact_endpoints_and_interpolation(db):
    demand_table(db)
    assert get_demand_from_wsfu(db,'IPC',10).value==30
    assert get_demand_from_wsfu(db,'IPC',20).value==60
    assert get_demand_from_wsfu(db,'IPC',15).value==45


def test_demand_no_extrapolation_below_or_above(db):
    demand_table(db)
    assert get_demand_from_wsfu(db,'IPC',9) is None
    assert get_demand_from_wsfu(db,'IPC',21) is None


def test_conflicting_demand_rows_are_not_arbitrarily_selected(db):
    tid=demand_table(db)
    for key,value in [('wsfu',10),('flush_tank_lpm',99)]:
        db.execute('INSERT INTO design_table_values(table_id,row_key,col_key,value_num) VALUES (?,?,?,?)',(tid,'conflict',key,value))
    with pytest.raises(ValueError,match='Conflicting'):get_demand_from_wsfu(db,'IPC',10)


def test_us_gpm_demand_is_normalized_without_losing_precision(db):
    demand_table(db)
    db.execute("UPDATE design_table_values SET col_key='flush_tank_gpm' WHERE col_key='flush_tank_lpm'")
    exact=get_demand_from_wsfu(db,'IPC',10)
    interpolated=get_demand_from_wsfu(db,'IPC',15)
    assert exact.unit=='L/min' and exact.value==pytest.approx(30*3.785411784)
    assert interpolated.value==pytest.approx(45*3.785411784,rel=1e-12)


def test_contradictory_flow_units_are_rejected(db):
    tid=demand_table(db)
    db.execute("INSERT INTO design_table_values(table_id,row_key,col_key,value_num) VALUES (?,'a','flush_tank_gpm',99)",(tid,))
    with pytest.raises(ValueError,match='Contradictory'):get_demand_from_wsfu(db,'IPC',10)


def payload(model='A'):
    p=empty_extract_payload(model+'.rvt','2026-10-26T00:00:00');p['revit_model_id']=model
    p['pipes']=[dict(revit_element_id='42',system='cold_water',length_m=10,nominal_diameter_mm=25,flow_lps=1)]
    return p


def test_same_element_id_in_two_models_is_distinct(db):
    import_revit_extract(db,1,payload('A'));import_revit_extract(db,1,payload('B'))
    assert db.execute('SELECT COUNT(DISTINCT pipe_id) FROM pipes WHERE project_id=1').fetchone()[0]==2
    with pytest.raises(ValueError,match='Multiple model'):export_results_for_revit(db,1)


def test_import_rollback_is_atomic(db):
    db.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON revit_elements BEGIN SELECT RAISE(ABORT,'SYNTHETIC'); END;")
    p=payload();p['fixtures']=[dict(revit_element_id='99',family='Synthetic',type_name='Synthetic')]
    with pytest.raises(sqlite3.IntegrityError):import_revit_extract(db,1,p)
    assert db.execute('SELECT COUNT(*) FROM pipes').fetchone()[0]==0


def test_model_edit_invalidates_prior_calculation(db):
    p=payload();import_revit_extract(db,1,p)
    pid=db.execute('SELECT pipe_id FROM pipes').fetchone()[0]
    save_calculation(db,1,velocity_from_flow(1,25,'T'),target_type='pipe',target_id=pid)
    p['pipes'][0]['flow_lps']=2;import_revit_extract(db,1,p)
    assert not export_results_for_revit(db,1)['results']
    assert db.execute('SELECT flow_lps FROM pipes').fetchone()[0]==2


def test_model_change_invalidates_project_network_dependencies(db):
    save_calculation(db,1,velocity_from_flow(1,25,'NETWORK'),target_type='network',target_id='N')
    import_revit_extract(db,1,payload())
    assert db.execute("SELECT is_current FROM calculations WHERE calc_id='NETWORK'").fetchone()[0]==0


def test_later_pass_does_not_hide_another_failed_pipe_check(db):
    import_revit_extract(db,1,payload())
    pipe_id=db.execute('SELECT pipe_id FROM pipes').fetchone()[0]
    failed=velocity_from_flow(1,25,'FAIL');failed.status='FAIL'
    save_calculation(db,1,failed,target_type='pipe',target_id=pipe_id)
    other=CalculationResult('PASS','different_check','synthetic',{}, {},1,'mm',status='PASS')
    save_calculation(db,1,other,target_type='pipe',target_id=pipe_id)
    result=export_results_for_revit(db,1)['results']['42']
    assert result['status']=='FAIL' and set(result['check_ids'])=={'FAIL','PASS'}


@pytest.mark.parametrize('change',[
    lambda p:p.update(pipes=None),
    lambda p:p['pipes'][0].update(length_m=float('nan')),
    lambda p:p['pipes'][0].update(nominal_diameter_mm=0),
    lambda p:p['pipes'][0].update(system=[]),
    lambda p:p['pipes'].append(dict(p['pipes'][0])),
    lambda p:p.update(fixtures=[dict(revit_element_id='99',family='F',type_name='T',parameters=[])]),
])
def test_malformed_model_import_has_validation_findings(db,change):
    p=payload();change(p)
    assert validate_extract_payload(p)
    with pytest.raises(InvalidExtractPayload):import_revit_extract(db,1,p)
    assert db.execute('SELECT COUNT(*) FROM pipes').fetchone()[0]==0
