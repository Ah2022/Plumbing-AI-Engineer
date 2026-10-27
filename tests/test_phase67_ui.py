"""Real UI actions on disposable projects; no live Revit writes."""
from tests.test_streamlit_app import fresh_app, _create_project


def test_report_review_packet_revision_and_proposal(fresh_app):
    at=_create_project(fresh_app)
    at.sidebar.radio[0].set_value('Hot Water').run(timeout=30)
    next(b for b in at.button if b.label=='Calculate heater capacity').click().run(timeout=30)
    assert not at.exception
    at.sidebar.radio[0].set_value('Report / Export').run(timeout=30)
    next(b for b in at.button if b.label=='Build reproducible review packet').click().run(timeout=30)
    assert not at.exception
    assert any(b.label=='Download review packet (JSON)' for b in at.get('download_button'))
    next(t for t in at.text_input if t.label=='Revision recorded by').set_value('Synthetic engineer')
    next(b for b in at.button if b.label=='Save immutable review revision').click().run(timeout=30)
    assert not at.exception and at.session_state['conn'].execute('SELECT COUNT(*) FROM review_snapshots').fetchone()[0]==1
    next(b for b in at.button if b.label=='Reproduce from recorded inputs').click().run(timeout=30)
    assert not at.exception
    next(t for t in at.text_input if t.label=='Override reviewer').set_value('Synthetic engineer')
    next(t for t in at.text_input if t.label=='Proposed value unit').set_value('kW')
    next(t for t in at.text_area if t.label=='Override reason and evidence').set_value('Synthetic reviewed selection')
    next(b for b in at.button if b.label=='Record override proposal').click().run(timeout=30)
    assert not at.exception and at.session_state['conn'].execute('SELECT COUNT(*) FROM calculation_overrides').fetchone()[0]==1


def test_revit_preview_import_linked_check_and_handoff(fresh_app):
    at=_create_project(fresh_app)
    at.sidebar.radio[0].set_value('Revit Exchange').run(timeout=30)
    next(b for b in at.button if b.label=='Preview synthetic Revit extract').click().run(timeout=30)
    assert not at.exception
    next(c for c in at.checkbox if c.label.startswith('I reviewed this model identity')).set_value(True).run(timeout=30)
    next(b for b in at.button if b.label=='Import reviewed extract').click().run(timeout=30)
    assert not at.exception
    next(n for n in at.number_input if n.label=='Reviewed internal bore (mm)').set_value(20.)
    next(n for n in at.number_input if n.label=='Reviewed design flow (L/s)').set_value(.2)
    next(t for t in at.text_input if t.label=='Linked-check reviewer / input evidence').set_value('SYNTHETIC known bore and flow')
    next(b for b in at.button if b.label=='Calculate linked pipe check').click().run(timeout=30)
    assert not at.exception and not at.error
    assert any(b.label=='Download Revit handoff JSON' for b in at.get('download_button'))
    row=at.session_state['conn'].execute("SELECT * FROM calculations WHERE target_type='pipe'").fetchone()
    assert row is not None and row['review_status']=='REVIEW_REQUIRED'


def test_release_page_runs_independent_benchmarks(fresh_app):
    at=_create_project(fresh_app)
    at.sidebar.radio[0].set_value('Release Readiness').run(timeout=30)
    next(b for b in at.button if b.label=='Run remaining-system benchmarks').click().run(timeout=30)
    assert not at.exception and next(m for m in at.metric if m.label=='Software benchmark status').value=='PASS'
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0
