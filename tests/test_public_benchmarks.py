"""Real public input execution, import security and non-approval contracts."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from validation import public_benchmarks as pb
from validation.gate import _entry_accepted,validation_gate
from solvers.service import configured_library


def test_sources_are_pinned_and_never_approval_eligible():
    data=pb.catalogue()
    assert len(data['sources'])==6 and len(data['cases'])==7
    for source in data['sources']:
        assert len(source['commit'])==40 and source['approval_eligible'] is False
    assert all(c['engineering_status']=='ENGINEERING_REVIEW_REQUIRED' and c['acceptance_eligible'] is False for c in data['cases'])
    for c in data['cases']:
        for a in c['artifacts']:
            assert c['commit'] in a['url'] and len(a['sha256'])==64 and len(a['git_blob_sha'])==40
    assert not any(a['redistribute'] for c in data['cases'] if c['repository'].startswith(('KIOS-Research','OpenWaterAnalytics')) for a in c['artifacts'])


def test_licensed_distributed_assets_match_pins_and_retain_notices():
    for c in pb.catalogue()['cases']:
        for a in c['artifacts']:
            if not a['redistribute']:continue
            raw=pb.artifact_path(a).read_bytes()
            assert pb.sha(raw)==a['sha256'] and len(raw)==a['bytes']
    data=pb.case('coordproof-ifc-semantic')
    assert {'model','inventory','license','notice'}=={a['role'] for a in data['artifacts']}


def test_import_is_exact_checksum_and_controlled_path(tmp_path,monkeypatch):
    c=deepcopy(pb.case('swmmcanada-dwf-fixture'));a=c['artifacts'][0];raw=pb.artifact_path(a).read_bytes()
    monkeypatch.setattr(pb,'case',lambda identity:c);monkeypatch.setattr(pb,'DATA',tmp_path)
    result=pb.import_bytes(c['id'],'model',raw)
    assert result['engineering_status']=='ENGINEERING_REVIEW_REQUIRED'
    with pytest.raises(ValueError,match='checksum'):pb.import_bytes(c['id'],'model',raw+b' ')
    a['local_path']='../../outside.inp'
    with pytest.raises(ValueError,match='Unsafe'):pb.import_bytes(c['id'],'model',raw)


@pytest.mark.parametrize('engine,text',[
    ('swmm','[OPTIONS]\nFLOW_UNITS LPS\n[FILES]\nSAVE HOTSTART C:\\outside.hsf'),
    ('swmm','[TIMESERIES]\nR FILE "../../private.txt"'),
    ('swmm','[LID_USAGE]\nC L 1 1 1 0 0 0 output.txt'),
    ('epanet','[OPTIONS]\nUNITS LPS\nHYDRAULICS USE outside.hyd'),
    ('epanet','[REPORT]\nFILE outside.txt'),
])
def test_native_external_file_interfaces_are_rejected(engine,text):
    with pytest.raises(ValueError):pb.screen_inp(text.encode(),engine)


def test_native_bounds_and_units_are_not_silently_changed():
    with pytest.raises(ValueError,match='LPS'):pb.screen_inp(b'[OPTIONS]\nUNITS GPM','epanet')
    text=b'[OPTIONS]\nFLOW_UNITS LPS\nSTART_DATE 01/01/2020\nEND_DATE 02/01/2020\n'
    with pytest.raises(ValueError,match='bounds'):pb.screen_inp(text,'swmm')


@pytest.mark.parametrize('options',['SPECIFIC GRAVITY 2','DEMAND MULTIPLIER 2','DEMAND MODEL PDA','PRESSURE KPA'])
def test_unmapped_fluid_demand_and_pressure_options_are_rejected(options):
    raw=('[OPTIONS]\nUNITS LPS\n'+options+'\n[JUNCTIONS]\nJ 0 1\n[RESERVOIRS]\nS 20\n[PIPES]\nP S J 10 50 140 0 OPEN').encode()
    with pytest.raises(ValueError):pb.epanet_model(raw)


def test_registered_sources_do_not_claim_executed_or_calibrated_results():
    for identity in ['swmmcanada-graham-creek','owa-epanet-example-source','gis-to-swmm-source']:
        r=pb.run_case(identity)
        assert r['software_status']=='SOURCE_REGISTERED_ONLY' and r['acceptance_eligible'] is False
        assert not r['comparisons'] and r['engineering_status']=='ENGINEERING_REVIEW_REQUIRED'


@pytest.mark.parametrize('identity,expected',[('swmmcanada-dwf-fixture','PASS'),('swmm-epa-linear-links','FAIL'),('coordproof-ifc-semantic','PASS')])
def test_actual_pinned_public_candidates_preserve_successes_and_failed_checks(identity,expected):
    r=pb.run_case(identity)
    assert r['software_status']==expected,r.get('issues')
    assert r['acceptance_eligible'] is False and r['code_compliance_status']=='NOT_EVALUATED'
    assert r['engineering_status']=='ENGINEERING_REVIEW_REQUIRED'
    if identity=='swmm-epa-linear-links':
        assert r['routing_continuity_error_pct']>1 and r['nonconverged_node_steps']>0
        assert next(x for x in r['comparisons'] if x['check']=='declared_steady_inflow_reaches_outfall_lps')['status']=='PASS'
    if identity.startswith('swmm'):
        assert r['normalized_flow_units']=='L/s' and r['execution_changes']


def test_hanoi_original_vs_mapped_engine_when_local_file_and_solver_are_present():
    c=pb.case('epanet-hanoi-local');library=configured_library()
    if not pb.artifact_path(c['artifacts'][0]).exists() or not library or not library.is_file():pytest.skip('Local-only source/model licence review or optional EPANET setup is pending')
    r=pb.run_case(c['id'],library=library)
    assert r['software_status']=='PASS',r.get('issues')
    assert all(x['status']=='PASS' for x in r['comparisons'])


def test_missing_or_changed_inputs_do_not_reuse_old_native_evidence(tmp_path,monkeypatch):
    monkeypatch.setattr(pb,'LOCAL',tmp_path)
    r=pb.run_case('epanet-hanoi-local')
    assert r['software_status']=='MISSING_INPUT'
    c=deepcopy(pb.case('swmmcanada-dwf-fixture'));c['artifacts'][0]['sha256']='0'*64
    monkeypatch.setattr(pb,'case',lambda identity:c)
    assert pb.run_case(c['id'])['software_status']=='INPUT_CHANGED'


def test_public_badges_cannot_be_promoted_to_engineering_acceptance():
    for tag in ('PUBLIC_BENCHMARK','REAL_OPEN_DATA_UNCALIBRATED','SOFTWARE_REFERENCE_ONLY','ENGINEERING_REVIEW_REQUIRED'):
        assert not _entry_accepted(dict(engineering_status='ACCEPTED',evidence_class='AUTHENTICATED_CODE_OR_APPROVED_PROJECT_REFERENCE',evidence_tags=[tag]))
    assert validation_gate()['public_benchmarks_acceptance_eligible'] is False


def test_public_result_save_rejects_promotion(tmp_path):
    r=pb.run_case('gis-to-swmm-source');path=pb.save_result(r,tmp_path)
    assert path.is_file()
    r['acceptance_eligible']=True
    with pytest.raises(ValueError,match='engineering acceptance'):pb.save_result(r,tmp_path)


def test_no_redirects_and_no_unknown_benchmark_urls():
    with pytest.raises(ValueError,match='redirect'):pb._NoRedirect().redirect_request(None,None,None,None,None,None)
    with pytest.raises(ValueError,match='Unknown'):pb.case('https://untrusted.example/model.inp')


def test_recorded_executions_are_source_bound_not_golden_engineering_targets():
    for identity,status in [('swmmcanada-dwf-fixture','PASS'),('swmm-epa-linear-links','FAIL'),('coordproof-ifc-semantic','PASS')]:
        r=pb.recorded_result(identity)
        assert r['software_status']==status and r['acceptance_eligible'] is False
        assert r['runner_sha256']==pb.runner_fingerprint()
        assert r['catalogue_sha256']==pb.sha(pb.CATALOGUE.read_bytes())
        assert r['input_sha256']=={a['role']:a['sha256'] for a in pb.case(identity)['artifacts']}
