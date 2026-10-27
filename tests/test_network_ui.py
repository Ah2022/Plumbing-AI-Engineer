import json
from tests.test_streamlit_app import fresh_app


def open_network(at):
    next(b for b in at.button if b.label=='Create project').click().run(timeout=30)
    at.sidebar.radio[0].set_value('Network Review').run(timeout=30)
    assert not at.exception
    return at


def test_water_network_review_saves_full_trace(fresh_app):
    at=open_network(fresh_app)
    next(b for b in at.button if b.label=='Run network review').click().run(timeout=30)
    assert not at.exception
    row=at.session_state['conn'].execute("SELECT * FROM calculations WHERE calc_type='water_network_check'").fetchone()
    assert row['review_status']=='REVIEW_REQUIRED'
    data=json.loads(row['intermediate_json'])
    assert data['governing_terminal']=='B' and len(data['pipes'])==3


def test_invalid_network_json_is_actionable(fresh_app):
    at=open_network(fresh_app)
    next(r for r in at.radio if r.label=='Network input method').set_value('Mapped network JSON').run(timeout=30)
    next(t for t in at.text_area if t.label=='Mapped network JSON').set_value('{not json}')
    next(b for b in at.button if b.label=='Run network review').click().run(timeout=30)
    assert not at.exception and at.error
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0


def test_drainage_missing_data_never_crashes_or_claims_full_compliance(fresh_app):
    at=open_network(fresh_app)
    next(s for s in at.selectbox if s.label=='Network type').set_value('Drainage and vents').run(timeout=30)
    next(b for b in at.button if b.label=='Run network review').click().run(timeout=30)
    assert not at.exception
    report=at.session_state['network_result']
    assert report['coverage_status']=='PARTIAL' and report['review_status']=='REVIEW_REQUIRED'


def test_cross_code_network_request_is_rejected(fresh_app):
    at=open_network(fresh_app)
    next(r for r in at.radio if r.label=='Network input method').set_value('Mapped network JSON').run(timeout=30)
    field=next(t for t in at.text_area if t.label=='Mapped network JSON')
    model=json.loads(field.value);model['code_id']='OTHER'
    field.set_value(json.dumps(model))
    next(b for b in at.button if b.label=='Run network review').click().run(timeout=30)
    assert not at.exception and at.error


def test_edited_supply_head_reaches_review(fresh_app):
    at=open_network(fresh_app)
    next(n for n in at.number_input if n.label=='Available supply head (m)').set_value(1)
    next(b for b in at.button if b.label=='Run network review').click().run(timeout=30)
    assert not at.exception
    assert at.session_state['network_result']['minimum_pressure_margin_m'] < 0
    row=at.session_state['conn'].execute("SELECT inputs_json FROM calculations WHERE calc_type='water_network_check'").fetchone()
    assert json.loads(row['inputs_json'])['network']['available_head_m']==1
