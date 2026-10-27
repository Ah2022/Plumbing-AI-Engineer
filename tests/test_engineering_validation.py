"""Independent candidate goldens, actual EPANET evidence and fail-closed acceptance."""
import ast
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
from zipfile import ZipFile
import pytest
from validation.adapter import DATA,load,reference_connection,run_method,run_project
from validation.gate import core_entrypoints,validation_gate
from validation.reference_math import project_worksheet,epanet_input,epanet_convention_pressures
from validation.suite import run_validation,review_bundle

PROJECTS=['residential','office','hotel','hospital','mixed_use']


@pytest.fixture
def reference_db():
    conn=reference_connection()
    yield conn
    conn.close()


@pytest.mark.parametrize('case',load('method-cases.json'),ids=lambda r:r['id'])
def test_method_against_frozen_independent_candidate(case,reference_db):
    result=run_method(case,reference_db)
    assert result['software_status']=='PASS',result
    assert result['engineering_status']=='REVIEW_REQUIRED'


@pytest.mark.parametrize('slug',PROJECTS)
def test_complete_building_candidate_golden(slug,reference_db):
    project=load(f'projects/{slug}/input.json');expected=load(f'projects/{slug}/expected.json')
    result=run_project(project,expected,reference_db)
    assert result['software_status']=='PASS',result['differences']
    assert result['warnings']==expected['expected_warnings']
    assert expected['unevaluated_checks'] and project['code_edition']=='IPC 2024'
    assert result['drainage']['coverage_status']=='PARTIAL'
    assert result['water']['review_status']=='REVIEW_REQUIRED'
    # Technical hydraulic pass/fail is distinct from pending code approval.
    assert result['water']['technical_status']==('FAIL' if slug=='hospital' else 'PASS')


@pytest.mark.parametrize('slug',PROJECTS)
def test_decimal_hand_worksheet_reproduces_frozen_numbers(slug):
    p=load(f'projects/{slug}/input.json');e=load(f'projects/{slug}/expected.json')
    assert project_worksheet(p)==e
    assert epanet_input(p)==(DATA/f'projects/{slug}/epanet.inp').read_text(encoding='ascii')
    # Declared independent path schedule must agree with source incidence/demand.
    m=p['water_model'];pipes={r['id']:r for r in m['pipes']};nodes={r['id']:r for r in m['nodes']}
    downstream={key:0 for key in pipes}
    for tid,path in p['hand_schedule']['terminal_paths'].items():
        current=m['root']
        for pid in path:
            assert pipes[pid]['from_node']==current
            current=pipes[pid]['to_node'];downstream[pid]+=nodes[tid]['design_flow_lps']
        assert current==tid
    assert downstream==p['hand_schedule']['pipe_flows_lps']


@pytest.mark.parametrize('slug',PROJECTS)
def test_actual_epanet_output_and_every_pressure_delta_explained(slug):
    p=load(f'projects/{slug}/input.json');e=load(f'projects/{slug}/expected.json');actual=load(f'projects/{slug}/epanet-results.json')
    assert actual['version']==20200
    assert actual['library_sha256']==load('epanet-provenance.json')['library_sha256']
    assert actual['input_sha256']==hashlib.sha256(epanet_input(p).encode('ascii')).hexdigest()
    for pid,row in e['pipes'].items():assert actual['pipes'][pid]['flow_lps']==pytest.approx(row['flow_lps'],abs=1e-6)
    predicted=epanet_convention_pressures(p)
    ledger={r['terminal']:r for r in load('discrepancies.json') if r['project_id']==slug and 'terminal' in r}
    assert set(ledger)==set(e['terminals'])
    for tid,row in e['terminals'].items():
        assert actual['nodes'][tid]['pressure_m']==pytest.approx(predicted[tid],abs=1e-6)
        assert actual['nodes'][tid]['pressure_m']-row['available_head_m']==pytest.approx(ledger[tid]['delta_m'],abs=1e-10)
        assert ledger[tid]['engineering_review']=='PENDING'
    assert actual['warnings']==([dict(operation='EN_solveH',code=6)] if slug=='hospital' else [])


def test_coverage_is_exhaustive_and_each_unreviewed_form_is_visible():
    coverage=load('coverage.json');gate=validation_gate()
    assert {r['entrypoint'] for r in coverage['core_calculations']}==core_entrypoints()
    assert gate['core_calculations']==29 and gate['interactive_forms']==103
    assert gate['pending_reference_entries']==132
    assert not gate['unregistered_calculations']
    assert not gate['authoritative'] and gate['release_label']=='ENGINEERING_VALIDATION_PENDING'
    assert all(p['reviewer_role']=='BIM MANAGER' and p['engineering_status']=='PENDING' for p in gate['projects'])


def test_new_supported_calculation_blocks_acceptance(monkeypatch):
    import validation.gate as module
    monkeypatch.setattr(module,'core_entrypoints',lambda:core_entrypoints()|{'calculations.new_method.unregistered'})
    result=module.validation_gate()
    assert result['unregistered_calculations']==['calculations.new_method.unregistered']
    assert not result['authoritative']


def test_engine_discrepancy_is_not_silently_accepted(reference_db):
    p=load('projects/office/input.json');e=load('projects/office/expected.json')
    p['water_model']['nodes'][-1]['design_flow_lps']*=1.1
    r=run_project(p,e,reference_db)
    assert r['software_status']=='FAIL'
    assert all(d['explanation']=='UNEXPLAINED_ENGINE_DISCREPANCY' for d in r['differences'])


def test_golden_mutation_and_incomplete_packages_block(tmp_path):
    copy=tmp_path/'references';shutil.copytree(DATA,copy)
    p=copy/'projects/office/expected.json';p.write_text('{}',encoding='utf-8')
    result=validation_gate(copy)
    assert not result['authoritative'] and any('changed or missing' in issue for issue in result['issues'])
    (copy/'coverage.json').unlink()
    assert not validation_gate(copy)['authoritative']


def test_approved_metadata_cannot_certify_synthetic_projects(tmp_path):
    copy=tmp_path/'references';shutil.copytree(DATA,copy)
    for folder in (copy/'projects').iterdir():
        p=folder/'input.json';value=json.loads(p.read_text());value['code_adoption']='APPROVED';p.write_text(json.dumps(value),encoding='utf-8')
        r=folder/'review.json';review=json.loads(r.read_text());review.update(decision='ACCEPTED',reviewer_name='Claimed reviewer',credentials='Claimed qualifications',qualified_plumbing_engineer=True,independent_of_implementation=True,signed_at='2026-10-27',signature_artifact_sha256='a'*64,source_authentication_evidence='Claimed evidence',input_sha256=hashlib.sha256(p.read_bytes()).hexdigest());r.write_text(json.dumps(review),encoding='utf-8')
    # Refresh hashes so the test exercises evidence class, not only integrity.
    manifest=json.loads((copy/'manifest.json').read_text())
    manifest['files']={name:hashlib.sha256((copy/name).read_bytes()).hexdigest() for name in manifest['files']}
    (copy/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    result=validation_gate(copy)
    assert not result['authoritative'] and all(p['engineering_status']=='PENDING' for p in result['projects'])


def test_accepted_flags_cannot_fill_missing_independent_calculation_references(tmp_path):
    copy=tmp_path/'references';shutil.copytree(DATA,copy)
    p=copy/'coverage.json';coverage=json.loads(p.read_text())
    for group in ('core_calculations','interactive_forms'):
        for entry in coverage[group]:entry['engineering_status']='ACCEPTED'
    p.write_text(json.dumps(coverage),encoding='utf-8')
    result=validation_gate(copy)
    assert result['pending_reference_entries']==132 and not result['authoritative']


def test_oracle_and_epanet_adapter_do_not_import_production_engine():
    for name in ('reference_math.py','epanet_runner.py'):
        tree=ast.parse((DATA.parent/name).read_text(encoding='utf-8'))
        imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        assert not any(s.startswith(('calculations','database','app','reports','workbooks','models')) for s in imports)


def test_suite_and_review_download_never_rewrite_goldens():
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.rglob('*') if p.is_file()}
    result=run_validation()
    assert result['software_status']=='PASS' and not result['engineering_gate']['authoritative']
    assert len(result['methods'])==26 and len(result['projects'])==5
    with ZipFile(BytesIO(review_bundle())) as z:
        assert len([p for p in z.namelist() if p.endswith('/review.json')])==5
        assert not any(p.endswith(('.db','.xlsx','.dll','.exe')) for p in z.namelist())
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


def test_release_benchmarks_cannot_grant_engineering_acceptance():
    from reports.release_checks import run_release_benchmarks
    result=run_release_benchmarks()
    assert result['software_status']=='PASS'
    assert result['release_label']=='ENGINEERING_VALIDATION_PENDING'
    assert not result['engineering_validation']['authoritative']


def test_phase1a_ui_runs_without_touching_project_calculations(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('PLUMBING_ENGINE_DB_PATH',str(tmp_path/'ui.db'))
    script="""
import streamlit as st
from database.db import init_db,get_connection,get_db_path
from app.release_page import page_release_readiness
from compliance.rule_loader import load_all_rules
if not get_db_path().exists():
    conn=init_db();load_all_rules(conn)
    conn.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES(1,'Synthetic UI','Office','IPC')");conn.commit()
else:
    conn=get_connection()
st.session_state.conn=conn;st.session_state.project_id=1
page_release_readiness()
"""
    at=AppTest.from_string(script).run(timeout=30)
    next(b for b in at.button if b.label=='Run five golden reference projects').click().run(timeout=30)
    assert not at.exception
    assert next(m for m in at.metric if m.label=='Golden comparison status').value=='PASS'
    assert any('Engineering validation pending' in r.value for r in at.warning)
    with sqlite3.connect(tmp_path/'ui.db') as conn:
        assert conn.execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0


@pytest.mark.skipif(not os.environ.get('EPANET_LIBRARY'),reason='Pinned EPANET library not installed; recorded actual runs tested above')
def test_live_external_epanet_run():
    result=run_validation(epanet_library=os.environ['EPANET_LIBRARY'])
    assert result['software_status']=='PASS'
    assert all(r['epanet']['mode']=='LIVE_EXTERNAL_RUN' for r in result['projects'])
