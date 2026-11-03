"""Conservation, analytical physics, domain exits and governance regressions."""
from copy import deepcopy
import json,math
import pytest
from engineering.registry import ROOT
from engineering.service import run_module
from solvers.service import configured_library,solve_network


def example(module):return json.loads((ROOT/f'examples/engineering/{module}.json').read_text())


def test_liquid_displacement_compresses_air_and_AAV_cannot_relieve_it():
    p=example('coupled_drainage');sealed=run_module(p);d=p['data']
    d['vents']=[dict(id='V',source_id='SYN',from_node='C1',to_node='ATM',kind='AAV',resistance_pa_s_m3=100000)]
    aav=run_module(p)
    assert aav['values']['maximum_air_gauge_magnitude_pa']==pytest.approx(sealed['values']['maximum_air_gauge_magnitude_pa'])
    d['vents'][0]['kind']='open';opened=run_module(p)
    assert opened['values']['maximum_air_gauge_magnitude_pa']<sealed['values']['maximum_air_gauge_magnitude_pa']
    assert opened['values']['final_air_mass_kg']<sealed['values']['final_air_mass_kg']
    assert abs(opened['values']['air_balance_error_kg'])<1e-12


def test_coupled_liquid_pressure_feedback_and_water_air_solids_mass():
    p=example('coupled_drainage');d=p['data'];d['inflows']=[]
    d['nodes'].append(dict(d['nodes'][0],id='C2',initial_air_absolute_kpa=100.1,initial_concentration_kg_m3=2))
    d['pipes']=[dict(id='P1',source_id='SYN',from_node='C2',to_node='C1',length_m=2,internal_mm=20,
        friction_factor=.02,fittings_k=1,port_from_m=0,port_to_m=0,initial_flow_lps=0)]
    result=run_module(p);v=result['values']
    assert v['final_liquid_m3']==pytest.approx(1)
    assert v['final_suspended_kg']+v['final_deposited_kg']==pytest.approx(1.5)
    assert any(row.get('flow_lps',0)>0 for row in result['trace'] if row['kind']=='pipe')
    assert all(abs(v[k])<1e-10 for k in ['liquid_balance_error_m3','air_balance_error_kg','solids_balance_error_kg'])
    # A smaller maximum step approaches the same coupled state.
    d['maximum_step_s']=.005;fine=run_module(p)
    coarse=next(row for row in reversed(result['trace']) if row['kind']=='pipe')
    finer=next(row for row in reversed(fine['trace']) if row['kind']=='pipe')
    assert coarse['flow_lps']==pytest.approx(finer['flow_lps'],abs=1e-6)


def test_trap_displacement_changes_air_volume_and_pressure():
    p=example('coupled_drainage');d=p['data'];sealed=run_module(p)
    d['traps']=[dict(id='T',source_id='SYN',node='C1',leg_area_m2=.01,effective_length_m=.2,seal_mm=100,damping_pa_s_m=1000)]
    coupled=run_module(p)
    assert coupled['values']['maximum_air_gauge_magnitude_pa']<sealed['values']['maximum_air_gauge_magnitude_pa']
    assert abs(coupled['values']['air_balance_error_kg'])<1e-12
    d['traps'][0]['seal_mm']=.1
    assert not run_module(p)['complete']


def test_phase_transition_and_high_concentration_are_explicitly_rejected():
    p=example('coupled_drainage');d=p['data'];d['nodes'].append(dict(d['nodes'][0],id='C2'))
    d['pipes']=[dict(id='P',source_id='SYN',from_node='C1',to_node='C2',length_m=2,internal_mm=600,friction_factor=.02,fittings_k=0,port_from_m=0,port_to_m=0,initial_flow_lps=0)]
    with pytest.raises(ValueError,match='submerged'):run_module(p)
    p=example('coupled_drainage');p['data']['nodes'][0]['initial_concentration_kg_m3']=100
    with pytest.raises(ValueError):run_module(p)


def test_full_frame_mechanism_rejected_and_reactions_balance_load():
    p=example('piping_flexibility');r=run_module(p)
    fixed=next(row for row in r['trace'] if row['kind']=='node' and row['id']=='A')
    assert fixed['reaction_fy_n']==pytest.approx(-100) and fixed['reaction_mz_nm']==pytest.approx(-200)
    p['data']['frame']['constraints']=[]
    with pytest.raises(ValueError,match='mechanism'):run_module(p)


def test_frame_3d_rotation_preserves_cantilever_solution():
    p=example('piping_flexibility');r=run_module(p);frame=p['data']['frame']
    frame['nodes'][1].update(x_m=0,y_m=0,z_m=2)
    frame['loads'][0].update(fy_n=0,fx_n=100)
    s=run_module(p)
    assert s['values']['maximum_translation_mm']==pytest.approx(r['values']['maximum_translation_mm'])
    assert s['values']['maximum_screened_von_mises_mpa']==pytest.approx(r['values']['maximum_screened_von_mises_mpa'])


def test_structure_borne_force_phasors_cancel_coherently():
    p=example('structure_borne');row=p['data']['spectrum'][0]
    row['excitations'].append(dict(row['excitations'][0],phase_rad=math.pi))
    r=run_module(p)
    assert r['values']['maximum_normal_rms_velocity_m_s']<1e-15
    p['data']['inertias'][0]['mass_kg']=0
    with pytest.raises(ValueError,match='positive lumped mass'):run_module(p)


def test_hot_water_cold_failure_shutoff_is_safe_but_demand_remains_unmet():
    p=example('hot_water_draw');d=p['data'];d['events'][0]['cold_available']=False
    protected=run_module(p)
    assert protected['values']['scald_exposure_fixture_s']==0
    assert protected['values']['unmet_draw_l']==pytest.approx(1) and protected['technical_status']=='FAIL'
    d['fixtures'][0]['cold_failure_close_s']=2
    slow=run_module(p)
    assert slow['values']['scald_exposure_fixture_s']==pytest.approx(2)
    assert slow['values']['mixed_delivery_l']==pytest.approx(.1,abs=1e-4)
    assert slow['technical_status']=='FAIL'


def test_stratified_tank_draw_advection_energy_and_buoyancy_mixing():
    p=example('hot_water_draw');d=p['data'];d['events']=[]
    d['layers'][0]['initial_temperature_c']=80;d['layers'][1]['initial_temperature_c']=40
    r=run_module(p)
    assert r['values']['final_tank_top_c']==pytest.approx(60)
    assert r['values']['final_tank_bottom_c']==pytest.approx(60)
    assert abs(r['values']['energy_balance_residual_j'])<1e-6
    assert r['values']['maximum_outlet_c'] is None
    p=example('hot_water_draw');d=p['data'];d['events'][0]['mixed_flow_lps']=1
    d['maximum_step_s']=1;d['fixtures'][0].update(response_time_s=.1,initial_hot_fraction=0)
    r=run_module(p)
    assert r['complete'] and abs(r['values']['energy_balance_residual_j'])<1e-5
    assert 20<r['values']['final_tank_bottom_c']<60


def test_hot_water_overlapping_events_rejected():
    p=example('hot_water_draw');p['data']['events'].append(deepcopy(p['data']['events'][0]))
    with pytest.raises(ValueError,match='overlap'):run_module(p)


def test_medical_gas_does_not_silently_substitute_AGSS_or_liquid_hydraulics():
    p=example('medical_gas');p['data']['service']='AGSS'
    with pytest.raises(ValueError):run_module(p)
    p=example('agss_network');p['data']['interfaces'][0].update(minimum_suction_kpa=0,maximum_suction_kpa=.01)
    assert run_module(p)['technical_status']=='FAIL'
    p['data']['network']['mode']='pressure'
    with pytest.raises(ValueError,match='AGSS calculation'):run_module(p)


def test_liquid_source_vaporizer_N_plus_one_heat_and_reserve_limits():
    p=example('liquid_gas_inventory');d=p['data'];r=run_module(p)
    assert r['values']['usable_liquid_mass_kg']==pytest.approx(700)
    d['vaporizers'][0]['rated_heat_w']=1000
    assert run_module(p)['technical_status']=='FAIL'
    d['vaporizers'][0]['rated_heat_w']=20000;d['parasitic_heat_w']=10000
    assert run_module(p)['values']['reserve_duration_h']<r['values']['reserve_duration_h']


@pytest.mark.parametrize('mutation',[
    lambda d:d['measurements'][0].update(uncertainty=.6),
    lambda d:d['measurements'][0].update(unit='ppm'),
    lambda d:d['measurements'][0].update(method='Unknown method'),
    lambda d:d['measurements'][0].update(location='Different outlet'),
    lambda d:d['measurements'][0].update(system_revision='OLD'),
    lambda d:d['measurements'][0].update(calibration_valid_until='2025-01-01'),
    lambda d:d['signoffs'][0].update(system_revision='OLD'),
])
def test_medical_commissioning_uncertainty_units_method_location_revision_and_calibration(mutation):
    p=example('medical_commissioning');mutation(p['data']);r=run_module(p)
    assert r['technical_status']=='FAIL' and r['values']['certification_status']=='NOT_ISSUED'


def test_pressure_zone_report_hash_and_global_PDA_representation():
    p=example('pressure_zones');r=run_module(p)
    assert r['values']['minimum_service_fraction']==1
    p['data']['zones'][0]['pda_required_m']=30
    r=run_module(p)
    assert r['technical_status']=='FAIL' and not r['complete']
    assert r['values']['zone_pda_profiles_represented'] is False
    p=example('pressure_zones');p['data']['model']['nodes'][0]['head_m']=45
    with pytest.raises(ValueError,match='stale'):run_module(p)


def test_pressure_zone_inadequate_service_and_unmapped_boundary_fail():
    p=example('pressure_zones');d=p['data'];d['zones'][0]['nodes']=['S']
    second=dict(d['zones'][0],id='Z2',nodes=['A']);d['zones'].append(second)
    with pytest.raises(ValueError,match='cover exactly'):run_module(p)
    d['boundaries']=[dict(link_id='P1',source_id='SYN',from_zone='Z1',to_zone='Z2',treatment='PRV',reference='Fictional boundary assertion')]
    assert run_module(p)['technical_status']=='FAIL'


def test_pressure_zone_audit_against_an_actual_native_EPANET_report():
    library=configured_library()
    if not library or not library.is_file():pytest.skip('Actual pressure-zone rerun requires configured EPANET 2.2')
    p=example('pressure_zones');native=solve_network(p['data']['model'],library=library)
    assert native['complete']
    p['data']['solver_report']=native;r=run_module(p)
    assert r['technical_status']=='PASS' and r['values']['minimum_service_fraction']==pytest.approx(1)
    p['data']['model']['nodes'][0]['head_m']=5
    p['data']['solver_report']=solve_network(p['data']['model'],library=library)
    r=run_module(p)
    assert r['technical_status']=='FAIL' and r['values']['minimum_service_fraction']<.5


def test_all_experimental_results_retain_pending_acceptance():
    from engineering.registry import EXPERIMENTAL
    for metadata in EXPERIMENTAL:
        r=run_module(example(metadata['id']))
        assert r['review_status']=='REVIEW_REQUIRED' and r['code_compliance_status']=='NOT_EVALUATED'
        assert r['coverage_status']=='PARTIAL' and r['source_status']=='SYNTHETIC'
