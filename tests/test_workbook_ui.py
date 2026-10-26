import json
import pytest
from tests.test_streamlit_app import fresh_app
from tests.test_workbooks import book


@pytest.fixture
def reference_ui(tmp_path,monkeypatch):
    import app.workbook_page as page
    from workbooks.library import describe
    b=book();b.update(functions={},macros=False,external_links=0,cached_errors=[])
    entry=describe(b,'00-Synthetic/Fixture.xlsm')
    source=tmp_path/'fixture';source.write_bytes(b'SYNTHETIC')
    monkeypatch.setattr(page,'catalog',lambda:dict(workbooks=[entry]))
    monkeypatch.setattr(page,'source_path',lambda entry:source)
    monkeypatch.setattr(page,'cached_source',lambda *args:b)
    return b


def open_page(at):
    next(b for b in at.button if b.label=='Create project').click().run(timeout=30)
    at.sidebar.radio[0].set_value('Calculation Sheets').run(timeout=30)
    assert not at.exception
    return at


def test_reference_scenario_saves_fresh_value_and_provenance(fresh_app,reference_ui):
    at=open_page(fresh_app)
    next(t for t in at.text_area if t.label=='Input overrides as JSON').set_value('{"Calc!A1":5}')
    next(b for b in at.button if b.label=='Recalculate selected cells').click().run(timeout=30)
    assert not at.exception
    row=at.session_state['conn'].execute("SELECT * FROM calculations WHERE calc_type='reference_workbook_scenario'").fetchone()
    report=json.loads(row['intermediate_json'])
    assert report['results'][0]['value']==20 and report['source_sha256']=='synthetic'
    assert row['status']=='CALCULATED_NOT_APPROVED' and row['review_status']=='REVIEW_REQUIRED'
    assert row['result_value'] is None


def test_unsupported_workbook_scenario_is_saved_as_unevaluated(fresh_app,reference_ui):
    reference_ui['sheets']['Calc']['cells']['C1']['formula']='WEIGHT2SUM(A1)'
    at=open_page(fresh_app)
    next(b for b in at.button if b.label=='Recalculate selected cells').click().run(timeout=30)
    assert not at.exception
    assert at.session_state['workbook_result']['results'][0]['status']=='NOT_EVALUATED'


def test_invalid_input_json_does_not_save_a_scenario(fresh_app,reference_ui):
    at=open_page(fresh_app)
    next(t for t in at.text_area if t.label=='Input overrides as JSON').set_value('{"Calc!A1":NaN}')
    next(b for b in at.button if b.label=='Recalculate selected cells').click().run(timeout=30)
    assert not at.exception and at.error
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM calculations').fetchone()[0]==0
