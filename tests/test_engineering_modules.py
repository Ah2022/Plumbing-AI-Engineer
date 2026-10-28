"""Fixed independent candidate arithmetic plus failure/coverage/source contracts."""
from copy import deepcopy
import json,math
from pathlib import Path
import pytest
from engineering.service import run_module,validate_envelope,METHODS
from engineering.registry import CASES,MODULES,exposure_status
from engineering.drainage import circular_section
from tools.validate_engineering import validate

CASES_DATA=json.loads(CASES.read_text(encoding='utf-8'))


def candidate(identity):return deepcopy(next(c for c in CASES_DATA if c['id']==identity)['input'])


@pytest.mark.parametrize('case',CASES_DATA,ids=lambda c:c['id'])
def test_fixed_reference_results(case):
    original=deepcopy(case['input']);result=run_module(original)
    for key,expected in case['expected_values'].items():
        value=result['values'][key]
        if isinstance(expected,(int,float)):assert value==pytest.approx(expected,abs=case['absolute_tolerance'],rel=0)
        else:assert value==expected
    assert result['technical_status']==case['expected_status'] and result['complete']==case['complete']
    assert original==case['input']
    assert result['review_status']=='REVIEW_REQUIRED' and result['code_compliance_status']=='NOT_EVALUATED'
    assert result['coverage_status']=='PARTIAL' and result['source_status']=='SYNTHETIC'
    assert set(result['values'])==set(result['units'])


def test_all_priorities_have_explicit_scopes_and_matching_software_evidence():
    metadata=exposure_status()
    assert set(m['priority'] for m in metadata)==set(range(1,13))
    assert set(METHODS)=={c['module'] for c in CASES_DATA}
    assert all(m['available'] for m in metadata)
    for m in metadata:
        assert all(m[k] for k in ('scope','required_source_data','not_evaluated','method_references','validation_status'))
        assert m['engineering_status']=='REVIEW_REQUIRED'
    assert validate()['software_status']=='PASS'


def test_stale_or_missing_validation_hides_calculation_controls(tmp_path,monkeypatch):
    import engineering.registry as module
    missing=tmp_path/'evidence.json';monkeypatch.setattr(module,'EVIDENCE',missing)
    assert all(not m['available'] for m in module.exposure_status() if m['id']!='general_pressure')
    missing.write_text(json.dumps({'software_status':'PASS','implementation_sha256':'wrong','reference_cases_sha256':'wrong'}),encoding='utf-8')
    assert not any(m['available'] for m in module.exposure_status() if m['id']!='general_pressure')


@pytest.mark.parametrize('change',[
    lambda p:p['data'].update(internal_mm=0),lambda p:p['data'].update(manning_n=True),
    lambda p:p['data'].update(slope_pct=float('nan')),lambda p:p['data'].update(slope_pct=-1),
    lambda p:p['data'].update(maximum_fill_ratio=.99),lambda p:p['data'].update(design_flow_lps=-1),
    lambda p:p['data'].update(extra_silent_assumption=1),lambda p:p['data'].update(source_id='MISSING'),
    lambda p:p.update(sources=[]),lambda p:p['sources'][0].update(verification_status='VERIFIED'),
    lambda p:p['sources'][0].update(revision=''),
])
def test_bad_domain_or_unattributed_data_fails_closed(change):
    p=candidate('gravity-half-full');change(p)
    with pytest.raises((ValueError,KeyError,TypeError)):run_module(p)


def test_nominal_minimum_is_separate_from_internal_bore():
    p=candidate('fixture-criteria');p['data']['fixtures'][0]['selected_internal_mm']=16
    assert run_module(p)['technical_status']=='PASS'
    p['data']['fixtures'][0].update(selected_nominal_mm=15,selected_internal_mm=30)
    assert run_module(p)['technical_status']=='FAIL'


def test_recirculation_loop_balance_and_actual_return_temperatures():
    r=run_module(candidate('recirculation-thermal'));a,b=r['trace']
    assert a['return_temperature_c']==pytest.approx(57.5) and b['return_temperature_c']==pytest.approx(57.5)
    assert a['loop_head_m']+a['additional_balancing_head_m']==pytest.approx(b['loop_head_m']+b['additional_balancing_head_m'])
    assert a['required_flow_lps']==pytest.approx(.05) and b['required_flow_lps']==pytest.approx(.025)


def test_circular_geometry_and_zero_flow_are_finite():
    half=circular_section(.1,.05)
    assert half['hydraulic_radius_m']==pytest.approx(.025)
    assert circular_section(.1,1e-10)['area_m2']>0
    p=candidate('gravity-half-full');p['data'].update(design_flow_lps=0,minimum_velocity_m_s=0)
    r=run_module(p)
    assert r['values']['normal_depth_m']==0 and r['values']['velocity_m_s']==0


def test_storage_conservation_dry_limit_and_curve_range():
    r=run_module(candidate('linear-storage-puls'))
    assert all(abs(s['mass_balance_residual_m3'])<1e-10 for s in r['trace'])
    assert r['values']['overall_mass_balance_residual_m3']==pytest.approx(0,abs=1e-10)
    p=candidate('linear-storage-puls');p['data']['initial_storage_m3']=1
    p['data']['hydrograph']=[{'time_s':0,'inflow_lps':0},{'time_s':10000,'inflow_lps':0}]
    dry=run_module(p);assert dry['trace'][-1]['dry_outflow_limited'] and dry['values']['final_computed_storage_m3']==0
    bad=candidate('linear-storage-puls');bad['data']['storage_rating'][1]['storage_m3']=0
    with pytest.raises(ValueError,match='increase strictly'):run_module(bad)


def test_unsupported_orifice_conditions_do_not_return_fake_capacity():
    p=candidate('orifice');p['data']['upstream_water_level_m']=1
    assert run_module(p)['technical_status']=='NOT_EVALUATED'
    p=candidate('orifice');p['data']['tailwater_level_m']=1.01
    assert not run_module(p)['complete']


def test_circuit_and_AAV_missing_conditions_are_not_approved():
    p=candidate('vent-circuit');p['data']['circuit_relief_verified']=False
    assert run_module(p)['technical_status']=='FAIL'
    p=candidate('vent-aav');p['data']['fixtures'][1]['floor']='L2'
    assert run_module(p)['technical_status']=='FAIL'
    p=candidate('vent-wet');p['data']['allowed_fixture_types']=['basin']
    assert run_module(p)['technical_status']=='FAIL'


def test_catalogue_rejections_include_ratings_npsh_and_no_extrapolation():
    p=candidate('pump-catalogue');r=run_module(p)
    assert r['values']['eligible_models']==['DEMO-P1']
    assert 'Pressure rating insufficient' in r['trace'][1]['rejection_reasons']
    p['data']['npsha_m']=1
    assert run_module(p)['values']['eligible_count']==0
    p=candidate('pump-catalogue');p['data']['duty_flow_lps']=100
    r=run_module(p);assert r['values']['eligible_count']==0
    assert all(any('outside published curve' in reason for reason in e['rejection_reasons']) for e in r['trace'])
    p=candidate('pump-catalogue');p['sources'][0]['type']='PROJECT'
    with pytest.raises(ValueError,match='manufacturer evidence'):run_module(p)


def test_backflow_direction_and_separate_system_policy_are_not_interchangeable():
    p=candidate('fire-separation');assert run_module(p)['technical_status']=='PASS'
    p['data']['links'][1].update(from_node='F',to_node='S')
    assert run_module(p)['technical_status']=='FAIL'
    p=candidate('fire-separation');p['data']['separation_policy']='separate_systems'
    assert run_module(p)['technical_status']=='FAIL'
    p=candidate('fire-separation');p['data']['domestic_reserved_m3']=50
    assert run_module(p)['technical_status']=='FAIL'


def test_absolute_pressure_vessel_and_transient_domains():
    p=candidate('thermal-vessel');p['data']['precharge_gauge_kpa']=400
    with pytest.raises(ValueError,match='precharge'):run_module(p)
    p=candidate('rapid-surge');p['data']['closure_time_s']=0
    with pytest.raises(ValueError):run_module(p)
    p=candidate('rapid-surge');p['data']['closure_model']='arbitrary_network_transient'
    with pytest.raises(ValueError,match='linear_velocity'):run_module(p)
    p=candidate('noise-screen');p['data'].pop('acoustic_limit_db')
    with pytest.raises(ValueError):run_module(p)
    p=candidate('noise-screen');p['data']['limit_metric']='dBC peak'
    with pytest.raises(ValueError,match='Acoustic metrics differ'):run_module(p)


def test_source_review_claims_cannot_grant_code_or_engineering_approval():
    p=candidate('fixture-criteria');p['sources'][0].update(type='CODE',verification_status='REVIEWED_AS_REPORTED',reviewed_by='Claimed source reviewer')
    r=run_module(p)
    assert r['source_status']=='REVIEWED_AS_REPORTED' and r['review_status']=='REVIEW_REQUIRED'
    assert r['code_compliance_status']=='NOT_EVALUATED'
    assert r['input_sha256']!=run_module(candidate('fixture-criteria'))['input_sha256']


def test_independent_module_reference_gaps_block_release_acceptance():
    from validation.gate import validation_gate
    result=validation_gate()
    assert result['pending_module_scopes']==len(MODULES)
    assert not result['authoritative']
