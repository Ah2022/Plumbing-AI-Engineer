import json
import pytest
from tests.test_streamlit_app import fresh_app
from tests.test_network_ui import open_network
from tests.test_general_solver import library,example
from tests.test_review_workflow import project
from solvers.service import solve_network
from app.general_network_page import save_general_result


def general(at):
    at=open_network(at)
    next(s for s in at.selectbox if s.label=='Network type').set_value('General pressure network').run(timeout=30)
    assert not at.exception
    return at


def test_general_graph_editor_and_missing_backend_are_actionable(fresh_app,monkeypatch):
    monkeypatch.delenv('PLUMBING_EPANET_LIBRARY',raising=False);monkeypatch.delenv('EPANET_LIBRARY',raising=False)
    at=general(fresh_app)
    assert at.get('graphviz_chart') and at.dataframe
    next(b for b in at.button if b.label=='Run general hydraulic simulation').click().run(timeout=30)
    assert not at.exception
    assert next(m for m in at.metric if m.label=='Hydraulic solver status').value=='BACKEND_UNAVAILABLE'
    assert any('not configured' in r.value for r in at.warning)
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0


def test_invalid_general_json_cannot_show_stale_solver_findings(fresh_app):
    at=general(fresh_app)
    next(r for r in at.radio if r.label=='General network input method').set_value('Mapped graph JSON').run(timeout=30)
    next(t for t in at.text_area if t.label=='General mapped network JSON').set_value('{invalid}').run(timeout=30)
    assert not at.exception and at.error
    assert not at.get('graphviz_chart')
    assert not any(b.label=='Save general-network review' for b in at.button)


def test_general_solver_ui_runs_and_saves_governed_review(fresh_app,library):
    at=general(fresh_app)
    next(b for b in at.button if b.label=='Run general hydraulic simulation').click().run(timeout=30)
    assert not at.exception
    assert next(m for m in at.metric if m.label=='Hydraulic solver status').value=='CONVERGED'
    next(b for b in at.button if b.label=='Save general-network review').click().run(timeout=30)
    assert not at.exception and not at.error
    row=at.session_state['conn'].execute("SELECT * FROM calculations WHERE calc_type='general_network_check'").fetchone()
    assert row['review_status']=='REVIEW_REQUIRED'
    result=json.loads(row['intermediate_json'])
    assert result['code_compliance_status']=='NOT_EVALUATED' and result['coverage_status']=='PARTIAL'


def test_general_result_stays_unapproved_even_with_approved_basis(project,library,monkeypatch):
    conn,pid=project
    result=solve_network(example(),library=library)
    monkeypatch.setattr('compliance.governance.context',lambda *a:dict(review_status='VERIFIED',fingerprint='test-approved-context'))
    identity=save_general_result(conn,pid,'LOOP-1',result)
    row=conn.execute('SELECT * FROM calculations WHERE calc_id=?',(identity,)).fetchone()
    assert row['review_status']=='REVIEW_REQUIRED'
    bad=dict(result,code_compliance_status='PASS')
    with pytest.raises(ValueError,match='cannot bypass'):save_general_result(conn,pid,'LOOP-2',bad)


def test_general_solver_ui_runs_seven_declared_scenarios(fresh_app,library):
    at=general(fresh_app)
    next(s for s in at.selectbox if s.label=='General-network example').set_value('24-hour pumps, tank and valve').run(timeout=30)
    next(b for b in at.button if b.label=='Run declared scenario analysis').click().run(timeout=30)
    assert not at.exception
    assert any(h.value=='Scenario findings' for h in at.subheader)
    assert any(b.label=='Download scenario findings' for b in at.get('download_button'))
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0
