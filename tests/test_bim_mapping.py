"""Topology and revision contracts; every source in this file is synthetic."""
from copy import deepcopy
import json
import pytest
from bim.mapping import initial_mapping,initial_boundaries,diagnostics,snapshot,compare_snapshots,save_snapshot,validate_snapshot
from tests.test_review_workflow import project


def inventory():
    objects=[]
    for uid,kind,system in [('P1','pipe','CW'),('P2','pipe','CW'),('F','fixture','FX'),('D','pipe','SW')]:
        objects.append(dict(source_id=uid,kind=kind,name=uid,system=system,source_class='Synthetic',length_m=10.,
            horizontal_run_m=9.99,axis_segment_count=1,ports=[dict(source_id=uid+':a',flow_direction='IN'),dict(source_id=uid+':b',flow_direction='OUT')]))
    return dict(format='IFC',model_id='SYNTHETIC',source_sha256='a'*64,objects=objects,
        connections=[dict(from_port='P1:b',to_port='P2:a',evidence='SYNTHETIC'),
            dict(from_port='P2:b',to_port='F:a',evidence='SYNTHETIC'),dict(from_port='F:b',to_port='D:a',evidence='SYNTHETIC')])


def mapped(inv):
    rows=initial_mapping(inv)
    for r in rows:
        r.update(service='drainage' if r['source_id']=='D' else 'cold_water',nominal_mm=25.,internal_mm=20.,
            design_flow_lps=.2,elevation_m=3.,engineering_reviewer='Synthetic reviewer',evidence_reference='Synthetic explicit source',
            invert_start_m=3.,invert_end_m=2.8,direction_confirmed=True)
        if r['source_id']=='F':r.update(fixture_requirements_reviewed=True,requires_water=True,requires_drainage=True)
    return rows


def checks(report):return [f['check'] for f in report['findings']]


def test_connected_fixture_has_both_services_and_no_inferred_approval():
    inv=inventory();result=diagnostics(inv,mapped(inv))
    assert 'fixture_without_connection' not in checks(result)
    assert 'open_ends' in checks(result)
    assert result['technical_status']=='PARTIAL' and result['code_compliance']=='NOT_EVALUATED'


def test_all_requested_diagnostics():
    inv=inventory();rows=mapped(inv)
    inv['connections']=[]
    rows[0]['design_flow_lps']=-.2
    rows[1]['elevation_m']=None
    rows[3]['invert_end_m']=4.
    found=set(checks(diagnostics(inv,rows)))
    assert {'open_ends','disconnected_components','reversed_flow','missing_elevations','impossible_slopes','fixture_without_connection'}<=found
    inv['objects'].append(deepcopy(inv['objects'][0]))
    duplicate=diagnostics(inv,rows)
    assert not duplicate['identity_valid'] and checks(duplicate)==['duplicate_ids','duplicate_ids','duplicate_ids']


def test_ifc_source_and_sink_conflict_and_external_ports_are_reported():
    inv=inventory();inv['objects'][0]['ports'][1]['flow_direction']='SOURCE'
    inv['objects'][1]['ports'][0]['flow_direction']='SOURCE'
    inv['connections'].append(dict(from_port='P1:a',to_port='outside:1'))
    result=diagnostics(inv,mapped(inv))
    assert 'reversed_flow' in checks(result) and 'external_connection' in checks(result)


def test_terminal_decisions_require_attribution_and_do_not_hide_other_open_ends():
    inv=inventory();b=initial_boundaries(inv);b[0]['intentional_terminal']=True
    with pytest.raises(ValueError,match='reviewer'):diagnostics(inv,mapped(inv),b)
    b[0].update(engineering_reviewer='Synthetic',evidence_reference='Source inlet')
    report=diagnostics(inv,mapped(inv),b)
    assert not any('P1:a' in f['detail'] for f in report['findings'])
    assert 'open_ends' in checks(report)


@pytest.mark.parametrize('field,value',[('internal_mm',True),('nominal_mm',0),('elevation_m',float('nan')),('include','yes'),('service','guess')])
def test_invalid_mapping_inputs_are_not_coerced(field,value):
    inv=inventory();rows=mapped(inv);rows[0][field]=value
    with pytest.raises(ValueError):diagnostics(inv,rows)


def test_duplicate_foreign_mapping_or_boundary_ids_fail():
    inv=inventory();rows=mapped(inv);rows[1]['source_id']='P1'
    with pytest.raises(ValueError,match='exactly once'):diagnostics(inv,rows)
    with pytest.raises(ValueError,match='foreign'):diagnostics(inv,mapped(inv),[dict(port_id='outside',intentional_terminal=False)])


def test_impossible_fall_and_multi_segment_unevaluated():
    inv=inventory();rows=mapped(inv);rows[-1]['invert_end_m']=-20
    assert 'impossible_slopes' in checks(diagnostics(inv,rows))
    inv['objects'][-1]['axis_segment_count']=2
    result=diagnostics(inv,rows)
    assert any(f['check']=='slope' and f['status']=='NOT_EVALUATED' for f in result['findings'])


def test_snapshot_integrity_and_revision_comparison(project):
    inv=inventory();rows=mapped(inv);a=snapshot(inv,rows,[],'Synthetic reviewer','R1')
    changed=deepcopy(inv);changed['objects'][0]['length_m']=12.;changed['connections']=[]
    b=snapshot(changed,rows,[],'Synthetic reviewer','R2')
    diff=compare_snapshots(a,b)
    assert diff['recalculation_required'] and diff['connections_changed'] and diff['objects'][0]['fields']==['length_m']
    assert not compare_snapshots(a,a)['recalculation_required']
    conn,pid=project;save_snapshot(conn,pid,a);save_snapshot(conn,pid,b);save_snapshot(conn,pid,a)
    assert conn.execute('SELECT count(*) FROM bim_extraction_snapshots').fetchone()[0]==2
    stored=json.loads(conn.execute('SELECT packet_json FROM bim_extraction_snapshots WHERE snapshot_sha256=?',(a['sha256'],)).fetchone()[0])
    assert stored==a
    tampered=deepcopy(a);tampered['payload']['mapping'][0]['internal_mm']=99
    with pytest.raises(ValueError,match='checksum'):validate_snapshot(tampered)


def test_cross_model_revision_comparison_is_rejected():
    inv=inventory();a=snapshot(inv,mapped(inv),[],'S','R1');inv['model_id']='OTHER'
    b=snapshot(inv,mapped(inv),[],'S','R2')
    with pytest.raises(ValueError,match='different model'):compare_snapshots(a,b)


def test_result_only_change_is_separate_from_source_model_revision():
    inv=inventory();a=snapshot(inv,mapped(inv),[],'S','R1')
    inv['objects'][0]['parameters']={'PLM_Result_Value':1.}
    b=snapshot(inv,mapped(inv),[],'S','R2')
    result=compare_snapshots(a,b)
    assert result['result_parameters_changed']==['P1'] and not result['objects'] and not result['recalculation_required']


def test_connection_order_does_not_require_recalculation():
    inv=inventory();a=snapshot(inv,mapped(inv),[],'S','R1');inv['connections'].reverse()
    b=snapshot(inv,mapped(inv),[],'S','R2')
    assert not compare_snapshots(a,b)['recalculation_required']
