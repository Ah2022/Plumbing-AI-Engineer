"""Analytical limits, cross-method comparisons, failures and provenance contracts."""
from copy import deepcopy
import json, math, subprocess
from pathlib import Path
import pytest
from engineering.service import run_module
from engineering.registry import ROOT
from engineering.catalogue import import_catalogue,export_catalogue
from database.ipc2024_fixtures import choices
from database.design_table_api import list_drainage_fixture_unit_choices


def example(module):return json.loads((ROOT/f'examples/engineering/{module}.json').read_text())


def test_medical_gas_standards_do_not_invent_demand_or_grant_adoption():
    p=example('medical_gas'); expected=run_module(p)
    for basis in ['HTM_02_01','SBC_NFPA_99','ISO_7396_1']:
        p['data']['standard_basis']=basis; r=run_module(p)
        assert r['values']==expected['values']
        assert r['review_status']=='REVIEW_REQUIRED' and r['code_compliance_status']=='NOT_EVALUATED'
    p['data']['standard_basis']='HC_2020'
    with pytest.raises(ValueError,match='Select HTM'):run_module(p)


@pytest.mark.parametrize('change,reason',[
    (lambda d:d.update(standard_edition=''),'standard_edition'),
    (lambda d:d.update(service='AGSS'),'service-specific'),
    (lambda d:d.update(reference_temperature_k=0),'reference_temperature'),
    (lambda d:d['demand_groups'][0].update(diversity=1.1),'diversity'),
    (lambda d:d['nodes'].append(dict(id='LOST',source_id='SYN')),'Disconnected'),
    (lambda d:d['pipes'][0].update(to_node='S'),'tree'),
    (lambda d:d.update(source_pressure_absolute_kpa=50),'absolute pressure'),
])
def test_gas_bad_or_inapplicable_inputs_fail_closed(change,reason):
    p=example('medical_gas');change(p['data'])
    with pytest.raises(ValueError,match=reason):run_module(p)


def test_reference_conditions_change_gas_mass_and_pressure_loss():
    p=example('medical_gas');r=run_module(p);p['data']['reference_pressure_absolute_kpa']=200;s=run_module(p)
    assert s['values']['mass_flow_kg_s']==pytest.approx(2*r['values']['mass_flow_kg_s'])
    assert s['values']['minimum_terminal_absolute_kpa']<r['values']['minimum_terminal_absolute_kpa']
    p['data']['plant_units'][0]['available']=False
    assert run_module(p)['technical_status']=='FAIL'


def test_shared_pipe_flow_accumulation_heat_conservation_and_controls():
    p=example('recirculation_network');d=p['data']
    for pipe in d['pipes']:pipe['ua_w_k']=1
    r=run_module(p);byid={row['id']:row for row in r['trace'] if row['kind']=='pipe'}
    assert byid['SUP']['selected_flow_lps']==pytest.approx(.1)
    assert byid['RET']['selected_flow_lps']==pytest.approx(.1)
    assert byid['A1']['selected_flow_lps']==pytest.approx(.05)
    assert r['values']['ambient_heat_loss_kwh']>0
    assert abs(r['values']['energy_residual_j'])<1e-6
    d['control']=dict(mode='thermostat',sensor_node='H',on_below_c=58,off_above_c=59)
    r=run_module(p)
    assert r['values']['control_switches']>=1 and r['values']['pump_on_time_s']<d['duration_s']
    d['circuits'][0]['pipe_ids']=['SUP','A1','RET']
    with pytest.raises(ValueError,match='closed path'):run_module(p)


def test_moc_matches_joukowsky_and_split_pipe_network():
    p=example('network_transient');r=run_module(p)
    assert r['values']['maximum_gauge_kpa']-980.665==pytest.approx(1000)
    d=p['data'];d['nodes'].append(dict(id='J',source_id='SYN',kind='junction',elevation_m=0,initial_head_m=100,demand_lps=0))
    pipe=d['pipes'][0];pipe.update(to_node='J',length_m=50,cells=5)
    other=dict(pipe,id='P2',from_node='J',to_node='V');d['pipes'].append(other)
    s=run_module(p)
    assert s['values']['maximum_gauge_kpa']==pytest.approx(r['values']['maximum_gauge_kpa'])
    d['pipes'][0]['initial_flow_lps']*=2
    with pytest.raises(ValueError,match='continuity'):run_module(p)


def test_transient_stops_at_cavitation_instead_of_extending_single_phase_solution():
    p=example('network_transient');d=p['data'];d['duration_s']=.6
    d['nodes'][1]['opening'][-1]['time_s']=.6
    d['nodes'][0].update(initial_head_m=90,fixed_head_m=90)
    d['nodes'][1].update(initial_head_m=90,valve_resistance_m_per_m6_s2=90/(math.pi*.1**2/4)**2)
    r=run_module(p)
    assert not r['complete'] and r['values']['cavitation_domain_exceeded']
    assert r['technical_status']=='FAIL' and r['values']['simulated_duration_s']<.6


def test_air_AAV_admits_air_but_cannot_relieve_positive_pressure():
    p=example('drainage_air');d=p['data'];d.update(duration_s=1,step_s=.1,report_step_s=.1)
    d['displacements'][0]['hydrograph'][-1]['time_s']=1;d['traps']=[]
    d['vents'][0]['kind']='AAV'
    positive=run_module(p)
    assert positive['values']['maximum_gauge_pa']==pytest.approx(20)
    for row in d['displacements'][0]['hydrograph']:row['air_flow_lps']=-1
    negative=run_module(p)
    assert negative['values']['minimum_gauge_pa']>-20
    d['nodes'][0]['air_volume_m3']=.0001
    r=run_module(p)
    # With the AAV open the finite vent resistance limits pressure; no positive relief is inferred.
    assert r['values']['maximum_gauge_pa']==0


def test_trap_and_air_domain_failure_stop_results():
    p=example('drainage_air');p['data']['traps'][0]['seal_mm']=1
    r=run_module(p)
    assert r['values']['trap_seal_breach'] and not r['complete'] and r['technical_status']=='FAIL'
    p=example('drainage_air');p['data']['maximum_pressure_ratio']=.0001
    r=run_module(p)
    assert r['values']['small_pressure_domain_exceeded'] and not r['complete']


def test_acoustics_requires_every_band_and_combines_energy():
    p=example('acoustic_prediction');r=run_module(p);p['data']['sources'].pop();s=run_module(p)
    assert r['values']['predicted_receiver_dba']-s['values']['predicted_receiver_dba']==pytest.approx(10*math.log10(2))
    p['data']['sources'][0]['spectrum'][0]['frequency_hz']=500
    with pytest.raises(ValueError,match='every declared frequency'):run_module(p)


def test_restraint_release_reduces_thermal_stress_without_inventing_flexibility():
    p=example('pipe_stress');r=run_module(p);p['data']['restraint_fraction']=0;s=run_module(p)
    assert r['values']['thermal_axial_stress_mpa']==-120
    assert s['values']['thermal_anchor_force_n']==0 and s['values']['maximum_von_mises_mpa']<r['values']['maximum_von_mises_mpa']
    p['data']['external_gauge_kpa']=2000
    with pytest.raises(ValueError,match='buckling'):run_module(p)


def test_relief_capacity_bases_are_not_interchangeable_and_need_manufacturer_sources():
    p=example('relief_selection');p['data']['catalogue'][0]['rating_basis']='ASME_PRESSURE_STEAM'
    r=run_module(p)
    assert r['technical_status']=='FAIL' and r['values']['eligible_count']==0
    assert 'basis mismatch' in ' '.join(r['trace'][0]['rejection_reasons'])
    p['sources'][0]['type']='PROJECT'
    with pytest.raises(ValueError,match='manufacturer evidence'):run_module(p)


@pytest.mark.parametrize('module,kind',[('equipment_selection','pump'),('relief_selection','relief')])
def test_manufacturer_csv_round_trip_preserves_curve_ratings_and_sources(module,kind):
    p=example(module);catalogue=p['data']['catalogue'];models,curves=export_catalogue(catalogue,kind)
    restored=import_catalogue(models.encode(),kind,curves.encode() if curves is not None else None)
    assert restored==catalogue
    p['data']['catalogue']=restored
    assert run_module(p)['technical_status']=='PASS'
    with pytest.raises(ValueError):import_catalogue(b'model,nonsense\nA,1\n',kind)


def test_ipc2024_fixture_catalogue_has_groups_occupancies_flow_bands_and_no_cross_code_borrowing(monkeypatch):
    fixture={c['fixture_id']:c for c in choices()}
    assert len(fixture)==33 and all(c['confidence']=='FLAGGED' for c in fixture.values())
    assert fixture['washer_residential']['unit_value']==2
    assert fixture['wc_private_16']['unit_value']==3 and fixture['wc_public_16']['unit_value']==4
    assert fixture['shower_258']['unit_value']==5 and fixture['floor_sink']['unit_value'] is None
    assert fixture['emergency_floor']['unit_value']==0
    assert len(list_drainage_fixture_unit_choices(None,'IPC','2024'))==33
    monkeypatch.setattr('database.design_table_api.get_table_records',lambda *a:[])
    assert list_drainage_fixture_unit_choices(None,'SAUDI_SBC_701','2024')==[]
    assert list_drainage_fixture_unit_choices(None,'IPC','2021')==[]


def test_swmm_plateau_against_independent_half_full_manning_and_continuity():
    p=example('dynamic_drainage');r=run_module(p)
    assert r['technical_status']=='PASS' and abs(r['values']['continuity_error_pct'])<.01
    row=next(x for x in r['trace'] if x['kind']=='pipe' and x['time_s']==600)
    flow=(math.pi*.1**2/8)*(.1/4)**(2/3)*math.sqrt(.01)/.013*1000
    assert row['flow_lps']==pytest.approx(flow,abs=.002)
    assert row['depth_m']==pytest.approx(.05,abs=.0001)
    assert row['velocity_m_s']==pytest.approx(flow/1000/(math.pi*.1**2/8),abs=.001)
    p['data']['routing_step_s']=.5
    fine=run_module(p)
    fine_row=next(x for x in fine['trace'] if x['kind']=='pipe' and x['time_s']==600)
    assert fine_row['flow_lps']==pytest.approx(row['flow_lps'],abs=.002)


def test_swmm_large_mass_discrepancy_fails_even_when_converged():
    p=example('dynamic_drainage');d=p['data'];d['duration_s']=600
    d['inflows'][0]['hydrograph']=[dict(time_s=0,flow_lps=2.5827153230263296),dict(time_s=600,flow_lps=2.5827153230263296)]
    r=run_module(p)
    assert r['values']['nonconverging_steps']==0
    assert abs(r['values']['continuity_error_pct'])>d['maximum_continuity_error_pct'] and r['technical_status']=='FAIL'


def test_swmm_backwater_can_reverse_flow():
    p=example('dynamic_drainage');d=p['data'];d.update(duration_s=100,report_step_s=10)
    d['inflows']=[];d['nodes'][1].update(outfall_type='FIXED',tailwater_head_m=1.05)
    r=run_module(p)
    assert any(x.get('flow_lps',0)<0 for x in r['trace'] if x['kind']=='pipe')
    assert r['review_status']=='REVIEW_REQUIRED' and r['code_compliance_status']=='NOT_EVALUATED'


def test_swmm_structured_boundary_rejects_includes_bad_ids_and_disconnected_geometry():
    from engineering.dynamic_drainage import _input
    p=example('dynamic_drainage')['data'];p['nodes'][0]['id']='J\n[FILES]'
    with pytest.raises(ValueError,match='letter'): _input(p)
    p=example('dynamic_drainage')['data'];p['inflows'][0]['hydrograph'][0]['time_s']=1
    with pytest.raises(ValueError,match='time zero'):_input(p)
    p=example('dynamic_drainage')['data'];p['pipes'][0]['from_node']='UNKNOWN'
    with pytest.raises(ValueError,match='endpoints'):_input(p)


def test_swmm_timeout_has_actionable_diagnostics(monkeypatch):
    def timeout(*a,**k):raise subprocess.TimeoutExpired('native-worker',45)
    monkeypatch.setattr('engineering.dynamic_drainage.subprocess.run',timeout)
    with pytest.raises(ValueError,match='Shorten the event'):run_module(example('dynamic_drainage'))
