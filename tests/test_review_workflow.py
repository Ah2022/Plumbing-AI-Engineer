"""Independent report/revision/provenance and remaining-system acceptance cases."""
import json
from copy import deepcopy
import pytest
from app.db_helpers import save_calculation
from calculations.hot_water import heater_capacity
from calculations.tanks import size_hot_water_storage_tank_from_demand
from calculations.pumps import select_pump_duty
from compliance.rule_loader import load_all_rules
from compliance.governance import calculation_is_current
from database.db import init_db
from models import CalculationResult, MissingCodeDataError
from reports.review_workflow import (build_review_packet, verify_review_packet, save_review_revision,
    compare_review_revisions, propose_override, review_readiness)
from reports.report_generator import generate_calculation_report_markdown
from reports.qaqc_dashboard import run_qaqc
from reports.replay import replay_calculation
from reports.release_checks import run_release_benchmarks


@pytest.fixture
def project(tmp_path):
    conn = init_db(tmp_path/'review.db'); load_all_rules(conn)
    for name in ('Synthetic reviewer project','Other project'):
        conn.execute("INSERT INTO projects(project_name,building_type,code_id) VALUES (?,'Office','IPC')",(name,))
    conn.commit()
    yield conn,1
    conn.close()


def saved(conn, pid, identity='HEAT-1'):
    result = heater_capacity(.5,15,60,identity)
    save_calculation(conn,pid,result,target_type='heater',target_id='H1')
    return result


def test_report_contains_inputs_intermediates_and_execution_fingerprints(project):
    conn,pid=project; saved(conn,pid)
    report = generate_calculation_report_markdown(conn,pid)
    assert 'Recorded inputs' in report and 'mass_flow_kg_s' in report
    assert 'Intermediate results and unresolved checks' in report and 'input SHA-256' in report
    assert '94.185' in report and 'REVIEW_REQUIRED' in report


def test_immutable_review_packet_and_project_revision_comparison(project):
    conn,pid=project; saved(conn,pid)
    packet = build_review_packet(conn,pid)
    assert verify_review_packet(packet)['project']['project_id']==pid
    bad=deepcopy(packet); bad['payload']['report']['project']['project_name']='Changed'
    with pytest.raises(ValueError,match='checksum'):
        verify_review_packet(bad)
    first=save_review_revision(conn,pid,'R1','Synthetic reviewer')
    stored=conn.execute('SELECT packet_json FROM review_snapshots WHERE snapshot_id=?',(first,)).fetchone()[0]
    saved(conn,pid,'HEAT-2')
    second=save_review_revision(conn,pid,'R2','Synthetic reviewer')
    diff=compare_review_revisions(conn,pid,first,second)
    assert diff['added']==['HEAT-2'] and 'HEAT-1' in diff['changed']
    assert stored==conn.execute('SELECT packet_json FROM review_snapshots WHERE snapshot_id=?',(first,)).fetchone()[0]
    with pytest.raises(ValueError,match='this project'):
        compare_review_revisions(conn,2,first,second)


def test_override_is_attributed_proposal_not_calculation_mutation(project):
    conn,pid=project; saved(conn,pid)
    before=dict(conn.execute('SELECT * FROM calculations').fetchone())
    propose_override(conn,pid,'HEAT-1','selected_value',120,'kW','Synthetic engineer','Independent selection evidence')
    assert dict(conn.execute('SELECT * FROM calculations').fetchone())==before
    assert conn.execute('SELECT review_status FROM calculation_overrides').fetchone()[0]=='REVIEW_REQUIRED'
    assert 'override proposal' in ' '.join(review_readiness(conn,pid)['issues'])
    assert 'Independent selection evidence' in generate_calculation_report_markdown(conn,pid)
    with pytest.raises(ValueError,match='this project'):
        propose_override(conn,2,'HEAT-1','result_value',10,'kW','Reviewer','Reason')


def test_replay_matches_and_rejects_tampered_inputs(project):
    conn,pid=project; saved(conn,pid)
    assert replay_calculation(conn,pid,'HEAT-1')['status']=='MATCH'
    conn.execute("UPDATE calculations SET inputs_json='{}' WHERE calc_id='HEAT-1'"); conn.commit()
    assert replay_calculation(conn,pid,'HEAT-1')['status']=='INPUT_CHECKSUM_MISMATCH'
    assert not calculation_is_current(conn,pid,conn.execute('SELECT * FROM calculations').fetchone())


def test_engine_fingerprint_change_is_not_silently_replayed(project):
    conn,pid=project; saved(conn,pid)
    conn.execute("UPDATE calculation_provenance SET engine_sha256='different'"); conn.commit()
    assert replay_calculation(conn,pid,'HEAT-1')['status']=='ENGINE_CHANGED'


def test_superseded_failure_does_not_poison_current_qaqc(project):
    conn,pid=project
    fail=heater_capacity(.5,15,60,'OLD'); fail.status='FAIL'
    save_calculation(conn,pid,fail,target_type='heater',target_id='H1')
    saved(conn,pid,'NEW')
    row=next(r for r in run_qaqc(conn,pid) if r['check_name']=='Calculation status summary')
    assert row['status']=='WARNING' and '1 current' in row['details'] and 'historical/stale' in row['details']
    assert 'FAIL' not in row['details']


def test_legacy_calculation_never_acquires_fabricated_engine_proof(project):
    conn,pid=project; saved(conn,pid)
    conn.execute('DELETE FROM calculation_provenance'); conn.commit()
    assert replay_calculation(conn,pid,'HEAT-1')['status']=='LEGACY_ENGINE_UNKNOWN'
    assert 'legacy calculation' in ' '.join(review_readiness(conn,pid)['issues'])


def test_remaining_systems_release_evidence_is_software_only():
    result=run_release_benchmarks()
    assert result['software_status']=='PASS' and len(result['cases'])==9
    assert result['engineering_status']=='REVIEW_REQUIRED' and result['live_writeback_status']=='NOT_VALIDATED'


def test_heater_rejects_boolean_temperature_and_storage_rejects_wrong_source():
    with pytest.raises(ValueError):
        heater_capacity(.5,False,60,'BAD')
    unrelated=CalculationResult('X','pump_duty_selection','test',{}, {},1,'kW',selected_value=2)
    with pytest.raises(ValueError,match='hot_water_demand'):
        size_hot_water_storage_tank_from_demand(unrelated,'BAD')


def test_pump_preserves_unrounded_head_before_power_calculation():
    result=select_pump_duty(100,1.000049,0,0,0,0,.5,'P')
    assert result.intermediate['unrounded_tdh_m']==1.000049
    assert result.result_value==round(1000*9.80665*.1*1.000049/.5/1000,4)
    assert result.intermediate['hydraulic_power_kw']==pytest.approx(1000*9.80665*.1*1.000049/1000)


def test_fractional_storm_slope_is_not_truncated_to_a_table_column(project):
    from calculations.stormwater import size_storm_drain_pipe
    conn,pid=project
    tid=conn.execute("INSERT INTO design_tables(code_id,domain,table_name,reference,status) VALUES ('IPC','storm','8_Rainfall_Intensity [pipe_mm+vertical_drain_lpm]','SYNTHETIC','POPULATED')").lastrowid
    for key,value in [('pipe_mm',100),('vertical_drain_lpm',1000),('horiz_5mm_m',1000)]:
        conn.execute("INSERT INTO design_table_values(table_id,row_key,col_key,value_num) VALUES (?,'0',?,?)",(tid,key,value))
    conn.commit()
    with pytest.raises(MissingCodeDataError):
        size_storm_drain_pipe(conn,'IPC',5,'BAD',orientation='horizontal',slope_mm_per_m=5.9)
