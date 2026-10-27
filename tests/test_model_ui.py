"""Model-intake UI checks with real synthetic files and throwaway project DBs."""
import json
import pytest
from tests.test_streamlit_app import fresh_app, _create_project


def open_model_page(at):
    at = _create_project(at)
    at.sidebar.radio[0].set_value('CAD / IFC Checks').run(timeout=30)
    assert not at.exception
    return at


def load_example(at):
    pytest.importorskip('ifcopenshell')
    next(b for b in at.button if b.label == 'Load synthetic model').click().run(timeout=30)
    assert not at.exception and not at.error
    return at


def test_model_page_opens_without_importing_optional_parsers(fresh_app):
    at = open_model_page(fresh_app)
    assert next(b for b in at.button if b.label == 'Inspect uploaded model').disabled


def test_model_review_requires_mapping_confirmation(fresh_app):
    at = load_example(open_model_page(fresh_app))
    next(b for b in at.button if b.label == 'Run and save model checks').click().run(timeout=30)
    assert not at.exception and any('Confirm the mapping' in e.value for e in at.error)
    assert at.session_state['conn'].execute("SELECT COUNT(*) FROM calculations WHERE calc_type='model_design_check'").fetchone()[0] == 0


def test_model_review_saves_trace_partial_coverage_and_scope(fresh_app, monkeypatch):
    at = load_example(open_model_page(fresh_app))
    import compliance.governance as governance
    original_context = governance.context
    monkeypatch.setattr(governance, 'context', lambda *args: dict(original_context(*args), review_status='VERIFIED'))
    editor = next(key for key in at.session_state if key.endswith('_mapping'))
    at.session_state[editor] = {'edited_rows': {0: dict(service='cold_water', internal_mm=25.,
        design_flow_lps=1., input_reference='SYNTHETIC measured bore and flow')}, 'added_rows': [], 'deleted_rows': []}
    next(t for t in at.text_input if t.label == 'Mapping reviewer / evidence reference').set_value('SYNTHETIC reviewed mapping')
    next(t for t in at.text_input if t.label == 'Water velocity criterion reference').set_value('SYNTHETIC project criterion')
    next(n for n in at.number_input if n.label.startswith('Project water velocity')).set_value(3.)
    next(c for c in at.checkbox if c.label.startswith('I reviewed')).set_value(True)
    next(b for b in at.button if b.label == 'Run and save model checks').click().run(timeout=30)
    assert not at.exception and not at.error
    conn = at.session_state['conn']
    row = conn.execute("SELECT * FROM calculations WHERE calc_type='model_design_check'").fetchone()
    assert row['project_id'] == 1 and row['target_type'] == 'model_design'
    assert row['review_status'] == 'REVIEW_REQUIRED' and row['status'] == 'WARNING'
    report = json.loads(row['intermediate_json'])
    assert report['coverage_status'] == 'PARTIAL'
    assert any(f['check_id'] == 'water_velocity' and f['status'] == 'PASS' for f in report['findings'])
    assert any(f['status'] == 'NOT_EVALUATED' for f in report['findings'])
    trace = json.loads(row['inputs_json'])
    assert trace['source_units']['length_scale_to_m'] == .001 and len(trace['source_objects']) == 3
    # Same model identity replaces the current review without deleting history.
    next(b for b in at.button if b.label == 'Run and save model checks').click().run(timeout=30)
    assert conn.execute("SELECT COUNT(*) FROM calculations WHERE calc_type='model_design_check'").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM calculations WHERE calc_type='model_design_check' AND is_current=1").fetchone()[0] == 1
    # Changing projects cannot display another project's imported model or findings.
    at.sidebar.radio[0].set_value('Project').run(timeout=30)
    next(b for b in at.button if b.label == 'Create project').click().run(timeout=30)
    at.sidebar.radio[0].set_value('CAD / IFC Checks').run(timeout=30)
    assert not at.exception
    assert not any(b.label == 'Run and save model checks' for b in at.button)
