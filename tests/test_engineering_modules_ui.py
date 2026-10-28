import json
import pytest
from tests.test_streamlit_app import fresh_app,_create_project
from tests.test_review_workflow import project
from engineering.registry import MODULES,ROOT
from engineering.service import run_module
from app.engineering_page import save_module_result


def open_modules(at,identity):
    at=_create_project(at)
    at.sidebar.radio[0].set_value('Engineering Modules').run(timeout=30)
    next(s for s in at.selectbox if s.label=='Engineering module').set_value(identity).run(timeout=30)
    assert not at.exception
    return at


@pytest.mark.parametrize('identity',[m['id'] for m in MODULES if m['id']!='general_pressure'])
def test_each_exposed_module_runs_its_interactive_example(fresh_app,identity):
    at=open_modules(fresh_app,identity)
    assert any('Validation:' in c.value for c in at.caption)
    assert any('Required source data:' in str(w.value) for w in at.markdown)
    next(b for b in at.button if b.label=='Calculate scoped engineering result').click().run(timeout=30)
    assert not at.exception and not at.error
    assert next(m for m in at.metric if m.label=='Supplied-criteria technical result').value=='PASS'
    assert any('Code compliance not evaluated' in c.value for c in at.caption)
    assert any(b.label=='Download engineering result and evidence' for b in at.get('download_button'))
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0


def test_pressure_module_opens_existing_general_solver(fresh_app):
    at=open_modules(fresh_app,'general_pressure')
    next(b for b in at.button if b.label=='Open general pressure-network solver').click().run(timeout=30)
    assert not at.exception
    assert at.sidebar.radio[0].value=='Network Review'
    assert next(s for s in at.selectbox if s.label=='Network type').value=='General pressure network'


def test_source_or_input_edits_hide_previous_result(fresh_app):
    at=open_modules(fresh_app,'gravity_flow')
    next(b for b in at.button if b.label=='Calculate scoped engineering result').click().run(timeout=30)
    assert not at.exception
    next(r for r in at.radio if r.label=='Engineering input method').set_value('Structured input JSON').run(timeout=30)
    field=next(t for t in at.text_area if t.label=='Engineering calculation data (JSON)')
    values=json.loads(field.value);values['design_flow_lps']=1
    field.set_value(json.dumps(values)).run(timeout=30)
    assert not at.exception
    assert not any(m.label=='Supplied-criteria technical result' for m in at.metric)


def test_saved_module_proof_stays_pending_with_verified_context(project,monkeypatch):
    conn,pid=project
    p=json.loads((ROOT/'examples/engineering/fixture_minimum.json').read_text(encoding='utf-8'))
    report=run_module(p)
    monkeypatch.setattr('compliance.governance.context',lambda *a:dict(review_status='VERIFIED',fingerprint='synthetic-approved-context'))
    identity=save_module_result(conn,pid,'FIXTURE-1','Synthetic recording reviewer',report)
    row=conn.execute('SELECT * FROM calculations WHERE calc_id=?',(identity,)).fetchone()
    assert row['review_status']=='REVIEW_REQUIRED'
    assert json.loads(row['intermediate_json'])['code_compliance_status']=='NOT_EVALUATED'
    assert json.loads(row['inputs_json'])['recorded_by']=='Synthetic recording reviewer'


def test_new_basis_revision_does_not_reuse_old_module_result(fresh_app,monkeypatch):
    revision=[1]
    monkeypatch.setattr('app.engineering_page.get_basis',lambda *a:{'revision':revision[0]})
    at=open_modules(fresh_app,'pump_system')
    next(b for b in at.button if b.label=='Calculate scoped engineering result').click().run(timeout=30)
    assert at.metric
    revision[0]=2;at.run(timeout=30)
    assert not at.exception and not any(m.label=='Supplied-criteria technical result' for m in at.metric)


def test_stale_evidence_hides_controls_but_keeps_scope_explicit(fresh_app,monkeypatch,tmp_path):
    monkeypatch.setattr('engineering.registry.EVIDENCE',tmp_path/'missing.json')
    at=open_modules(fresh_app,'gravity_flow')
    assert not at.exception and at.error
    assert any('Calculation scope:' in str(m.value) for m in at.markdown)
    assert any('Validation:' in c.value for c in at.caption)
    assert not any(b.label=='Calculate scoped engineering result' for b in at.button)
