"""General graph contracts and actual EPANET 2.2 hydraulic acceptance cases."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from solvers.graph import normalize_graph,apply_scenario
from solvers.epanet_input import build_input
from solvers.service import solve_network,run_scenarios,routing,legacy_to_graph,compare_tree,configured_library

ROOT=Path(__file__).resolve().parents[1]


def example(name='loop'):
    return json.loads((ROOT/f'examples/pressure_{name}.json').read_text(encoding='utf-8'))


@pytest.fixture
def library():
    lib=configured_library()
    if not lib or not lib.is_file():pytest.skip('Optional EPANET2.2 library absent; pure graph, routing and failure contracts still tested')
    return lib


@pytest.mark.parametrize('slug',['residential','office','hotel','hospital','mixed_use'])
def test_tree_numbers_and_input_remain_exactly_unchanged(slug):
    from calculations.network import analyze_water_network
    m=json.loads((ROOT/f'validation/phase1a/projects/{slug}/input.json').read_text())['water_model'];before=deepcopy(m)
    expected=analyze_water_network(m)
    result=solve_network(m)
    assert result['backend']=='tree' and result['result']==expected and m==before


def test_routing_loop_pda_storage_and_eps():
    assert routing(example())['topology']['has_loops']
    assert 'pressure-dependent demand' in routing(example('pda'))['reasons']
    route=routing(example('eps'))
    assert route['backend']=='epanet' and {'tank storage','pump/valve equipment','extended-period simulation'}<=set(route['reasons'])
    with pytest.raises(ValueError,match='require EPANET'):routing(example(),backend='tree')


@pytest.mark.parametrize('mutate',[
    lambda m:m.update(units='US'),
    lambda m:m['nodes'].append(deepcopy(m['nodes'][0])),
    lambda m:m['links'][0].update(internal_mm=0),
    lambda m:m['links'][0].update(internal_mm=True),
    lambda m:m['links'][0].update(roughness_unit='mm'),
    lambda m:m['links'][0].update(from_node='UNKNOWN'),
    lambda m:m['nodes'][1].update(demand_lps=float('nan')),
    lambda m:m['nodes'][1].update(demand_lps=-1),
    lambda m:m['nodes'][1].update(id='NODE\n[OPTIONS]'),
    lambda m:m['links'][0].update(nominal_mm=50),
    lambda m:m.update(arbitrary_inp_text='[OPTIONS]'),
    lambda m:m.update(simulation={'duration_s':604801}),
    lambda m:m.update(simulation={'hydraulic_step_s':1}),
    lambda m:m.update(demand_model={'type':'PDA','minimum_pressure_m':10,'required_pressure_m':5,'exponent':.5,'reference':'Synthetic'}),
    lambda m:m.update(controls=[dict(link_id='UNKNOWN',status='CLOSED',condition='elapsed_time',time_s=1,reference='Synthetic')]),
    lambda m:m['nodes'][0].update(kind='junction',head_m=None),
])
def test_malformed_or_ambiguous_models_are_rejected(mutate):
    m=example();mutate(m)
    with pytest.raises((ValueError,TypeError,KeyError)):normalize_graph(m)


def test_new_graph_normalization_is_explicit_and_does_not_mutate_inputs():
    m=example();before=deepcopy(m);n,t=normalize_graph(m)
    assert m==before and n is not m and t['has_loops']
    assert n['demand_model']['type']=='DDA'
    assert n['simulation']['duration_s']==0


def test_invalid_pump_curve_tank_valve_and_scenario_targets():
    changes=[lambda m:m['curves']['CURVE']['points'][1].update(head_m=99),
        lambda m:m['nodes'][-1].update(initial_level_m=100),
        lambda m:next(e for e in m['links'] if e['kind']=='valve').update(setting_unit='psi'),
        lambda m:m['scenarios'][0].update(source_heads_m={'A':1})]
    for change in changes:
        m=example('eps');change(m)
        with pytest.raises(ValueError):normalize_graph(m)


def test_fire_demand_remains_unpatterned_and_closures_disable_reopening_controls():
    m=example('eps');before=deepcopy(m)
    closed,disabled=apply_scenario(m,dict(id='FAIL',label='Pump failure',reference='Synthetic',unavailable_links=['PUMP']))
    assert len(disabled)==2 and not closed['controls']
    assert next(e for e in closed['links'] if e['id']=='PUMP')['status']=='CLOSED'
    fire,_=apply_scenario(m,dict(id='FIRE',label='Fire load',reference='Synthetic',fire_demands_lps={'B':3}))
    b=next(n for n in fire['nodes'] if n['id']=='B')
    assert b['demand_lps']==1.8 and b['fire_demand_lps']==3
    assert 'B 3 PLM_FLAT FIRE' in build_input(fire)
    assert m==before


def test_backend_unavailable_does_not_silently_run_a_tree(monkeypatch):
    monkeypatch.delenv('PLUMBING_EPANET_LIBRARY',raising=False);monkeypatch.delenv('EPANET_LIBRARY',raising=False)
    r=solve_network(example())
    assert r['solver_status']=='BACKEND_UNAVAILABLE' and not r['complete'] and not r['snapshots']
    assert r['code_compliance_status']=='NOT_EVALUATED' and r['review_status']=='REVIEW_REQUIRED'
    assert 'PLUMBING_EPANET_LIBRARY' in r['diagnostics'][0]['action']


def test_timeout_and_worker_failure_are_actionable(tmp_path,monkeypatch):
    fake=tmp_path/'library';fake.write_bytes(b'not loaded by mocked worker')
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('solver',kwargs['timeout'])
    monkeypatch.setattr('solvers.service.subprocess.run',timeout)
    r=solve_network(example(),library=fake,timeout_s=.01)
    assert r['solver_status']=='TIMEOUT' and not r['complete'] and r['technical_status']=='NOT_EVALUATED'
    assert r['diagnostics'][0]['action']
    monkeypatch.setattr('solvers.service.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=1))
    assert solve_network(example(),library=fake)['solver_status']=='NOT_CONVERGED'


def test_legacy_unsupported_losses_and_darcy_factor_are_not_discarded():
    m=json.loads((ROOT/'examples/water_network.json').read_text())
    m['pipes'][0]['equipment_loss_m']=1
    with pytest.raises(ValueError,match='cannot be discarded'):legacy_to_graph(m)
    m['pipes'][0]['equipment_loss_m']=0;m['materials']['DEMO']['method']='darcy_weisbach'
    with pytest.raises(ValueError,match='no equivalent'):legacy_to_graph(m)
    m['simulation']={'duration_s':3600}
    with pytest.raises(ValueError,match='Advanced features'):solve_network(m)


def test_closed_legacy_pipe_routes_explicitly_and_storage_cannot_be_ignored():
    m=json.loads((ROOT/'examples/water_network.json').read_text())
    m['pipes'][0]['status']='CLOSED'
    assert routing(m)['backend']=='epanet'
    assert legacy_to_graph(m)['links'][0]['status']=='CLOSED'
    with pytest.raises(ValueError,match='requires EPANET'):routing(m,'tree')
    m['nodes'][1]['kind']='tank'
    with pytest.raises(ValueError,match='storage fields'):routing(m)


def test_controls_preserve_the_declared_pump_speed():
    m=example('eps');m['links'][0]['speed']=2
    inp=build_input(m)
    assert 'PUMP S J HEAD CURVE SPEED 2' in inp
    assert 'PUMP OPEN' not in inp
    assert 'LINK PUMP 2 IF NODE T BELOW 2' in inp


def test_loop_solution_against_symmetric_hand_balance(library):
    m=example();m['nodes'][1]['demand_lps']=0;m['nodes'][2]['demand_lps']=2
    r=solve_network(m,library=library);step=r['snapshots'][0]
    assert r['complete'] and r['solver_status']=='CONVERGED'
    # Two equal two-pipe paths deliver1L/s each to B; published EPANET feet/cfs convention.
    q=1/28.317;d=75/304.8
    loss=.3048*(4.727*(100/.3048)*q**1.852/(140**1.852*d**4.871)+.02517*q*q/d**4)
    b=next(n for n in step['nodes'] if n['node_id']=='B')
    assert b['pressure_m']==pytest.approx(40-10-2*loss,abs=1e-6)
    assert all(abs(e['flow_lps'])==pytest.approx(1,abs=1e-6) for e in step['links'])
    assert any(e['flow_lps']<0 for e in step['links'])
    assert r['code_compliance_status']=='NOT_EVALUATED'


def test_pda_delivered_flow_against_independent_pressure_equation(library):
    m=example('pda');r=solve_network(m,library=library);a=next(n for n in r['snapshots'][0]['nodes'] if n['node_id']=='A')
    def pressure(q_lps):
        q=q_lps/28.317;d=50/304.8
        return 5-.3048*(4.727*(100/.3048)*q**1.852/(140**1.852*d**4.871)+.02517*q*q/d**4)
    lo,hi=0.,2.
    for _ in range(100):
        q=(lo+hi)/2
        if q>2*math.sqrt(max(0,pressure(q))/20):hi=q
        else:lo=q
    assert a['delivered_demand_lps']==pytest.approx((lo+hi)/2,abs=1e-5)
    assert a['requested_demand_lps']==2 and a['demand_deficit_lps']>1
    assert r['technical_status']=='FAIL' and r['solver_status']=='CONVERGED'


@pytest.mark.parametrize('speed,expected_head',[ (1,27),(2,93)])
def test_pump_curve_point_and_affinity_speed(library,speed,expected_head):
    m=example('eps');m['nodes']=[m['nodes'][0],m['nodes'][1],dict(m['nodes'][2],demand_lps=5*speed,demand_pattern=None)]
    m['links']=[m['links'][0],m['links'][1]];m['links'][0]['speed']=speed
    m['simulation']['duration_s']=0;m['controls']=[];m['scenarios']=[];m['demand_model']={'type':'DDA','reference':'Synthetic fixed flow'}
    r=solve_network(m,library=library)
    assert r['complete'],r['diagnostics']
    j=next(n for n in r['snapshots'][0]['nodes'] if n['node_id']=='J')
    assert j['head_m']==pytest.approx(expected_head,abs=1e-6)


def test_eps_tank_continuity_and_elapsed_pump_controls(library):
    m=example('eps');m['simulation']['duration_s']=10800
    m['controls']=[dict(link_id='PUMP',status=status,condition='elapsed_time',time_s=time,reference='Synthetic timed control') for status,time in [('CLOSED',3600),('OPEN',7200)]]
    r=solve_network(m,library=library)
    assert r['complete'] and r['snapshots'][-1]['time_s']==10800
    for step in r['snapshots']:
        p=next(e for e in step['links'] if e['link_id']=='PUMP')
        if 3600<=step['time_s']<7200:assert p['status']=='CLOSED' and p['flow_lps']==pytest.approx(0,abs=1e-10)
    for a,b in zip(r['snapshots'],r['snapshots'][1:]):
        ta=next(n for n in a['nodes'] if n['kind']=='tank');tb=next(n for n in b['nodes'] if n['kind']=='tank')
        flow=next(e for e in a['links'] if e['link_id']=='PT')['flow_lps']
        # EPANET2.2 rounds LPS/cfs to28.317 while geometric volume uses0.3048^3.
        # Reconcile published conversions rather than widening conservation tolerance.
        delta=flow*(b['time_s']-a['time_s'])/28.317*.3048**3
        assert tb['volume_m3']-ta['volume_m3']==pytest.approx(delta,abs=1e-7)
    assert len(r['snapshots'])>=4


def test_all_seven_scenarios_and_held_failures(library):
    m=example('eps');before=deepcopy(m);r=run_scenarios(m,library=library)
    assert len(r['scenarios'])==7 and m==before
    assert all(s['result']['complete'] for s in r['scenarios'])
    failed=next(s for s in r['scenarios'] if s['scenario']['id']=='PUMP_FAILURE')
    assert len(failed['disabled_controls'])==2
    assert all(next(e for e in t['links'] if e['link_id']=='PUMP')['status']=='CLOSED' for t in failed['result']['snapshots'])
    assert r['code_compliance_status']=='NOT_EVALUATED'
    assert next(s for s in r['scenarios'] if s['scenario']['id']=='PEAK')['result']['technical_status']=='FAIL'


def test_prv_setting_and_multiple_headloss_equations(library):
    m=example('pda');m['demand_model']={'type':'DDA','reference':'Synthetic'}
    m['nodes'][0]['head_m']=50;m['nodes'][1]['demand_lps']=1
    up=dict(m['nodes'][1],id='U',demand_lps=0,required_pressure_m=0)
    m['nodes'].append(up);m['links'][0]['to_node']='U'
    m['links'].append(dict(id='PRV',kind='valve',from_node='U',to_node='A',internal_mm=50,valve_type='PRV',setting=15,setting_unit='m',reference='Synthetic'))
    r=solve_network(m,library=library)
    assert r['complete'],r['diagnostics']
    assert next(n for n in r['snapshots'][0]['nodes'] if n['node_id']=='A')['pressure_m']==pytest.approx(15,abs=1e-6)
    for equation,roughness,unit in [('D-W',.01,'mm'),('C-M',.01,'s/m^(1/3)')]:
        other=example('pda');other['simulation']={'headloss':equation};other['links'][0].update(roughness=roughness,roughness_unit=unit)
        assert solve_network(other,library=library)['complete']


@pytest.mark.parametrize('kind,setting,unit',[('FCV',2,'L/s'),('PSV',45,'m'),('PBV',10,'m')])
def test_flow_and_pressure_valve_regulation(library,kind,setting,unit):
    m=example('pda');m['demand_model']={'type':'DDA','reference':'Synthetic valve reference'}
    source=dict(m['nodes'][0],head_m=50);up=dict(m['nodes'][1],id='U',demand_lps=0,required_pressure_m=0)
    down=dict(up,id='D');tank=dict(id='T',kind='tank',elevation_m=0,initial_level_m=5,min_level_m=1,max_level_m=10,diameter_m=5,reference='Synthetic receiving tank')
    m['nodes']=[source,up,down,tank];a=dict(m['links'][0],from_node='S',to_node='U');b=dict(a,id='P2',from_node='D',to_node='T')
    valve=dict(id='V',kind='valve',from_node='U',to_node='D',internal_mm=50,valve_type=kind,setting=setting,setting_unit=unit,reference='Synthetic valve')
    m['links']=[a,valve,b];r=solve_network(m,library=library)
    assert r['complete'],r['diagnostics']
    step=r['snapshots'][0];v=next(e for e in step['links'] if e['link_id']=='V')
    if kind=='FCV':
        # Active FCV has finite conductance1/CBIG in EPANET2.2 hydcoeffs.c.
        # Its exact, exposed regularization residual is head_drop_ft*28.317/1e8.
        residual=v['head_drop_m']/.3048*28.317/1e8
        assert v['flow_lps']-2==pytest.approx(residual,abs=1e-10)
        assert v['flow_setting_residual_lps']==pytest.approx(residual,abs=1e-10)
    if kind=='PBV':assert v['head_drop_m']==pytest.approx(10,abs=1e-6)
    if kind=='PSV':assert next(n for n in step['nodes'] if n['node_id']=='U')['pressure_m']==pytest.approx(45,abs=1e-6)


def test_fire_category_is_not_reduced_by_domestic_zero_pattern(library):
    m=example('eps');m['simulation']['duration_s']=0;m['patterns']['DAY'][0]=0
    m['demand_model']={'type':'DDA','reference':'Synthetic fixed load test'}
    fire,_=apply_scenario(m,dict(id='FIRE',label='Fire load',reference='Synthetic',fire_demands_lps={'B':3}))
    r=solve_network(fire,library=library);b=next(n for n in r['snapshots'][0]['nodes'] if n['node_id']=='B')
    assert b['requested_demand_lps']==3 and b['delivered_demand_lps']==pytest.approx(3,abs=1e-6)


def test_nonconvergence_is_not_a_successful_or_approved_result(library):
    m=example();m['simulation']={'trials':1,'accuracy':1e-10}
    r=solve_network(m,library=library)
    assert not r['complete'] and r['solver_status']=='NOT_CONVERGED'
    assert r['technical_status']=='NOT_EVALUATED' and r['code_compliance_status']=='NOT_EVALUATED'
    assert any(d['severity']=='ERROR' and d['action'] for d in r['diagnostics'])


@pytest.mark.parametrize('slug',['residential','office','hotel','hospital','mixed_use'])
def test_equivalent_tree_backend_comparisons(library,slug):
    m=json.loads((ROOT/f'validation/phase1a/projects/{slug}/input.json').read_text())['water_model']
    r=compare_tree(m,library=library)
    assert r['epanet']['complete'] and len(r['comparison'])==2
    assert all(row['comparison_status']=='MATCH_WITH_DOCUMENTED_CONVENTIONS' for row in r['comparison'])
    assert all(abs(row['convention_residual_m'])<1e-6 for row in r['comparison'])
