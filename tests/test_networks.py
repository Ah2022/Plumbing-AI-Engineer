"""Independent synthetic network benchmarks and unsupported-model cases."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from calculations.network import analyze_water_network,analyze_drainage_network,validate_tree
from calculations.vent import check_trap_arm,check_vent_arrangement,size_vent_pipe_multidim
from calculations.drainage import size_drainage_pipe
from database.db import init_db
from models import MissingCodeDataError
from units.convert import gpm_to_lps,lps_to_gpm,ft_to_m,m_to_ft

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def water(): return json.loads((ROOT/'examples/water_network.json').read_text())


@pytest.fixture
def drainage(): return json.loads((ROOT/'examples/drainage_network.json').read_text())


@pytest.fixture
def tables(tmp_path):
    conn=init_db(tmp_path/'synthetic.db')
    conn.execute("INSERT INTO codes(code_id,code_name) VALUES ('TEST','Synthetic verification, not a code')")
    def add(domain,name,rows):
        cur=conn.execute("INSERT INTO design_tables(code_id,domain,table_name,reference,status) VALUES ('TEST',?,?,?,'POPULATED')",(domain,name,'SYNTHETIC_TEST_ONLY'))
        for i,row in enumerate(rows):
            for key,value in row.items():
                conn.execute('INSERT INTO design_table_values(table_id,row_key,col_key,value_num,confidence) VALUES (?,?,?,?,?)',(cur.lastrowid,str(i),key,value,'CONFIRMED'))
    add('drainage','5_Drainage_Sizing',[
        {'pipe_mm':50,'max_dfu_horiz_branch':4,'max_dfu_stack_le3_bi':8,'max_dfu_stack_gt3_bi':20,'max_dfu_per_branch_interval':2,'slope_10mm':4,'slope_20mm':6},
        {'pipe_mm':75,'max_dfu_horiz_branch':10,'max_dfu_stack_le3_bi':20,'max_dfu_stack_gt3_bi':40,'max_dfu_per_branch_interval':6,'slope_10mm':10,'slope_20mm':12},
        {'pipe_mm':100,'max_dfu_horiz_branch':20,'max_dfu_stack_le3_bi':40,'max_dfu_stack_gt3_bi':100,'max_dfu_per_branch_interval':20,'slope_10mm':20,'slope_20mm':30}])
    add('drainage','6_Min_Slope',[{'pipe_size_mm':50,'min_slope_pct':2},{'pipe_size_mm':75,'min_slope_pct':1},{'pipe_size_mm':100,'min_slope_pct':1}])
    add('vent','7_Vent_Sizing',[
        {'fu':2,'vent_mm':32},{'fu':4,'vent_mm':40},{'fu':8,'vent_mm':50},
        {'trap_arm_in':1.5,'max_dist_trap_to_vent_ft':3},
        {'stack_in':4,'fu':20,'vent_in':2,'max_len_ft':100}])
    conn.commit();yield conn;conn.close()


def test_pressure_path_hand_calculation(water):
    result=analyze_water_network(water)
    def loss(q_lps,length):
        q=q_lps/1000;d=.046;v=q/(math.pi*d*d/4)
        return 10.67*length*q**1.852/(140**1.852*d**4.8704)+v*v/(2*9.80665)
    expected=40-11-loss(2,20)-loss(1,40)-8
    assert result['minimum_pressure_margin_m']==pytest.approx(expected,abs=1e-10)
    assert result['governing_terminal']=='B'
    assert result['governing_path']==['P0','P2']
    assert result['technical_status']=='PASS' and result['review_status']=='REVIEW_REQUIRED'


def test_explicit_flows_conserve_each_branch(water):
    result=analyze_water_network(water)
    flows={r['pipe_id']:r['flow_lps'] for r in result['pipes']}
    assert flows=={'P0':2,'P1':1,'P2':1}


def test_governing_path_changes_with_outlet_requirement(water):
    water['nodes'][2]['required_residual_head_m']=35
    assert analyze_water_network(water)['governing_terminal']=='A'


def test_equipment_and_fittings_losses_are_included(water):
    base=analyze_water_network(water)
    water['pipes'][2]['equipment_loss_m']=3
    changed=analyze_water_network(water)
    assert changed['minimum_pressure_margin_m']==pytest.approx(base['minimum_pressure_margin_m']-3)
    water['pipes'][2]['fittings_k']=20
    assert analyze_water_network(water)['minimum_pressure_margin_m']<changed['minimum_pressure_margin_m']


def test_inadequate_source_cannot_be_fixed_by_arbitrary_size(water):
    water['available_head_m']=5
    result=analyze_water_network(water,select_sizes=True)
    assert result['technical_status']=='FAIL'
    assert result['minimum_pressure_margin_m']<0


def test_greedy_selection_meets_velocity_nominal_and_pressure(water):
    result=analyze_water_network(water,select_sizes=True)
    assert result['technical_status']=='PASS'
    assert all(r['velocity_m_s']<=2 and r['nominal_mm']>=20 for r in result['pipes'])
    assert all(r['margin_m']>=0 for r in result['terminals'])
    assert any(r['nominal_mm']!=r['internal_mm'] for r in result['pipes'])


def test_pressure_can_govern_upsize_after_velocity(water):
    water['velocity_limit_m_s']=10
    initial=deepcopy(water)
    for p in initial['pipes']: p['selected_size_id']='S20'
    assert analyze_water_network(initial)['technical_status']=='FAIL'
    result=analyze_water_network(water,select_sizes=True)
    assert result['technical_status']=='PASS'
    assert any(r['internal_mm']>16 for r in result['pipes'])


def test_no_available_size_is_explicit(water):
    water['catalogues']['DEMO']=water['catalogues']['DEMO'][:1]
    with pytest.raises(MissingCodeDataError,match='No catalogue size'):
        analyze_water_network(water,select_sizes=True)


def test_source_units_equivalence(water):
    result=analyze_water_network(water)
    for n in water['nodes']:
        n['elevation_m']=ft_to_m(m_to_ft(n['elevation_m']))
        if 'design_flow_lps' in n:n['design_flow_lps']=gpm_to_lps(lps_to_gpm(n['design_flow_lps']))
    assert analyze_water_network(water)['minimum_pressure_margin_m']==pytest.approx(result['minimum_pressure_margin_m'],abs=1e-10)


def test_darcy_model_requires_explicit_factor(water):
    water['materials']['DEMO']=dict(method='darcy_weisbach',friction_factor=.02,reference='Synthetic factor')
    assert analyze_water_network(water)['technical_status']=='PASS'
    del water['materials']['DEMO']['friction_factor']
    with pytest.raises(ValueError): analyze_water_network(water)


def test_wsfu_aggregation_keeps_continuous_demands_separate(water):
    water['flow_basis']='wsfu_table'
    for n in water['nodes']:
        if n.get('kind')=='fixture': n.pop('design_flow_lps');n['water_wsfu']=2
    water['nodes'][2]['continuous_flow_lps']=.2
    def lookup(w): return dict(flow_lps=w/10,unit='L/s',reference='Synthetic test transfer function')
    r=analyze_water_network(water,demand_lookup=lookup)
    rows={p['pipe_id']:p for p in r['pipes']}
    assert rows['P0']['water_wsfu']==4 and rows['P0']['flow_lps']==pytest.approx(.6)
    assert rows['P1']['flow_lps']==pytest.approx(.4)


def test_wrong_demand_units_cannot_silently_enter_solver(water):
    water['flow_basis']='wsfu_table'
    for n in water['nodes']:
        if n.get('kind')=='fixture': n.pop('design_flow_lps');n['water_wsfu']=2
    with pytest.raises(MissingCodeDataError):
        analyze_water_network(water,demand_lookup=lambda w:dict(flow_lps=w,unit='gpm',reference='Synthetic'))


@pytest.mark.parametrize('mutation',[
    lambda m:m['nodes'].append(deepcopy(m['nodes'][0])),
    lambda m:m['pipes'][0].update(to_node='UNKNOWN'),
    lambda m:m['pipes'].append(dict(m['pipes'][0],id='CYCLE',from_node='B',to_node='S')),
    lambda m:m['pipes'].pop(),
    lambda m:m['nodes'][2].update(elevation_m=float('nan')),
    lambda m:m['nodes'][2].update(design_flow_lps=-1),
    lambda m:m['nodes'][2].update(dfu=5),
    lambda m:m.update(service='combined_undefined'),
    lambda m:m.update(units='UNKNOWN'),
    lambda m:m['catalogues']['DEMO'][0].update(internal_mm=0),
    lambda m:m['pipes'][0].update(length_m=0),
    lambda m:m['pipes'][0].pop('losses_reference'),
    lambda m:m['nodes'][2].pop('required_residual_head_m'),
])
def test_invalid_water_models_are_rejected(water,mutation):
    mutation(water)
    with pytest.raises((ValueError,MissingCodeDataError)): analyze_water_network(water)


def test_drainage_cumulative_loads_and_geometry(tables,drainage):
    r=analyze_drainage_network(tables,'TEST',drainage)
    rows={p['pipe_id']:p for p in r['pipes']}
    assert rows['D0']['drainage_dfu']==4
    assert rows['D1']['drainage_dfu']==1 and rows['D2']['drainage_dfu']==3
    assert all(p['actual_slope_pct']==5 for p in r['pipes'])
    assert r['coverage_status']=='PARTIAL' and r['technical_status']=='WARNING'


def test_drainage_insufficient_capacity_is_failure(tables,drainage):
    drainage['nodes'][3]['drainage_dfu']=5
    drainage['pipes'][0]['nominal_mm']=50
    assert analyze_drainage_network(tables,'TEST',drainage)['technical_status']=='FAIL'


def test_fixture_minimum_is_separate_from_dfu_capacity(tables,drainage):
    drainage['pipes'][0].update(nominal_mm=50,minimum_nominal_mm=75)
    r=analyze_drainage_network(tables,'TEST',drainage)
    assert next(p for p in r['pipes'] if p['pipe_id']=='D0')['technical_status']=='FAIL'


def test_geometry_slope_below_reviewed_minimum_fails(tables,drainage):
    drainage['pipes'][0]['minimum_slope_pct']=6
    assert analyze_drainage_network(tables,'TEST',drainage)['technical_status']=='FAIL'


def test_adverse_gravity_fall_fails(tables,drainage):
    drainage['nodes'][1]['elevation_m']=-1
    assert analyze_drainage_network(tables,'TEST',drainage)['technical_status']=='FAIL'


def test_unknown_tables_are_missing_data_not_pass(tables,drainage):
    result=analyze_drainage_network(tables,'MISSING',drainage)
    assert all(p['technical_status']=='MISSING_DATA' for p in result['pipes'])


def test_building_drain_slope_column_rounds_conservatively(tables):
    a=size_drainage_pipe(tables,'TEST',5,'building_drain','D-1',selected_slope_pct=1.5)
    b=size_drainage_pipe(tables,'TEST',5,'building_drain','D-2',selected_slope_pct=2)
    assert a.result_value==75 and b.result_value==50
    with pytest.raises(MissingCodeDataError):
        size_drainage_pipe(tables,'TEST',5,'building_drain','D-3',selected_slope_pct=.1)


def test_stack_interval_limit_can_govern(tables,drainage):
    drainage['pipes'][0].update(context='stack_gt3_branch_intervals',branch_intervals=4,nominal_mm=50)
    drainage['nodes'][2]['branch_interval']=1
    drainage['nodes'][3]['branch_interval']=1
    r=analyze_drainage_network(tables,'TEST',drainage)
    main=next(p for p in r['pipes'] if p['pipe_id']=='D0')
    assert main['required_nominal_mm']==75 and main['technical_status']=='FAIL'


def test_stack_without_interval_mapping_is_not_passed(tables,drainage):
    drainage['pipes'][0].update(context='stack_gt3_branch_intervals',branch_intervals=4)
    r=analyze_drainage_network(tables,'TEST',drainage)
    assert next(p for p in r['pipes'] if p['pipe_id']=='D0')['technical_status']=='MISSING_DATA'


def test_stack_offset_is_explicitly_unevaluated(tables,drainage):
    drainage['pipes'][0]['has_offset']=True
    r=analyze_drainage_network(tables,'TEST',drainage)
    assert next(p for p in r['pipes'] if p['pipe_id']=='D0')['technical_status']=='NOT_EVALUATED'


def test_trap_arm_distance_boundary_and_failure(tables):
    assert check_trap_arm(tables,'TEST',38.1,.9144,'T-1').status=='PASS'
    assert check_trap_arm(tables,'TEST',38.1,.9145,'T-2').status=='FAIL'
    with pytest.raises(MissingCodeDataError):check_trap_arm(tables,'TEST',99,1,'T-3')


def test_special_vent_arrangements_never_default_to_pass(tables):
    for arrangement in ('wet','circuit','aav','unknown'):
        assert check_vent_arrangement(tables,'TEST',dict(id='V',arrangement=arrangement),4)['technical_status']=='NOT_EVALUATED'


def test_dry_vent_size_and_trap_distance(tables):
    v=dict(id='V',arrangement='dry',selected_nominal_mm=40,developed_length_m=3,trap_arm={'nominal_mm':38.1,'developed_length_m':.5})
    assert check_vent_arrangement(tables,'TEST',v,4)['technical_status']=='PASS'
    v['selected_nominal_mm']=32
    assert check_vent_arrangement(tables,'TEST',v,4)['technical_status']=='FAIL'


def test_missing_trap_geometry_preserves_review(tables):
    v=dict(id='V',arrangement='dry',selected_nominal_mm=40,developed_length_m=3)
    assert check_vent_arrangement(tables,'TEST',v,4)['technical_status']=='WARNING'


def test_multidimensional_vent_checks_all_coordinates(tables):
    r=size_vent_pipe_multidim(tables,'TEST',4,20,100,'V-1')
    assert r.result_value==2 and r.result_unit=='in'
    with pytest.raises(MissingCodeDataError):size_vent_pipe_multidim(tables,'TEST',4,21,100,'V-2')
    with pytest.raises(MissingCodeDataError):size_vent_pipe_multidim(tables,'TEST',4,20,101,'V-3')
