import json
import pytest
from tests.test_streamlit_app import fresh_app


@pytest.fixture
def reference_ui(tmp_path,monkeypatch):
    import app.interactive_page as page
    monkeypatch.setattr(page,'LOCAL',tmp_path/'no-local-workbooks')


def open_page(at):
    next(b for b in at.button if b.label=='Create project').click().run(timeout=30)
    at.sidebar.radio[0].set_value('Calculation Sheets').run(timeout=30)
    assert not at.exception
    return at


def test_reference_scenario_saves_fresh_value_and_provenance(fresh_app,reference_ui):
    at=open_page(fresh_app)
    next(n for n in at.number_input if n.label=='Flow rate (L/s)').set_value(3)
    next(n for n in at.number_input if n.label=='Duration (minutes)').set_value(20)
    next(b for b in at.button if b.label=='Calculate and save').click().run(timeout=30)
    assert not at.exception
    row=at.session_state['conn'].execute("SELECT * FROM calculations WHERE calc_type='reference_workbook_scenario'").fetchone()
    report=json.loads(row['intermediate_json'])
    assert report['results'][0]['value']==3600 and report['package_sha256']
    assert row['status']=='CALCULATED_NOT_APPROVED' and row['review_status']=='REVIEW_REQUIRED'
    assert row['result_value'] is None
    assert not at.text_area and not at.get('json')


def test_changed_draft_is_identified_and_retained_across_navigation(fresh_app,reference_ui):
    at=open_page(fresh_app)
    next(b for b in at.button if b.label=='Calculate and save').click().run(timeout=30)
    next(n for n in at.number_input if n.label=='Flow rate (L/s)').set_value(4).run(timeout=30)
    assert any('Inputs have changed' in w.value for w in at.warning)
    at.sidebar.radio[0].set_value('Code Profiles').run(timeout=30)
    at.sidebar.radio[0].set_value('Calculation Sheets').run(timeout=30)
    assert next(n for n in at.number_input if n.label=='Flow rate (L/s)').value==4


def test_imported_package_runs_without_local_excel_files(fresh_app,reference_ui):
    from workbooks.interactive import install_project_packages,build_package
    from workbooks.demo import demo_package
    at=fresh_app
    next(b for b in at.button if b.label=='Create project').click().run(timeout=30)
    p=build_package(demo_package()['workbook'],'Project-specific calculator.xlsx')
    install_project_packages(at.session_state['conn'],1,[p])
    at.sidebar.radio[0].set_value('Calculation Sheets').run(timeout=30)
    picker=next(s for s in at.selectbox if s.label=='Calculation')
    picker.set_value(p['package_sha256']).run(timeout=30)
    next(b for b in at.button if b.label=='Calculate and save').click().run(timeout=30)
    assert not at.exception and at.session_state['workbook_result']['report']['results'][0]['value']==1200
    assert not at.get('json')


def test_in_app_import_button_installs_a_portable_package(fresh_app,reference_ui,monkeypatch):
    import app.interactive_page as page
    from workbooks.demo import demo_package
    from workbooks.interactive import encode_package
    class Upload:
        name='interactive.plmcalc'
        def getvalue(self):return encode_package(demo_package())
    monkeypatch.setattr(page.st,'file_uploader',lambda *args,**kwargs:[Upload()])
    at=open_page(fresh_app)
    next(b for b in at.button if b.label=='Import and convert').click().run(timeout=30)
    assert not at.exception
    assert at.session_state['conn'].execute('SELECT COUNT(*) FROM project_calculation_packages').fetchone()[0]==1
    next(b for b in at.button if b.label=='Calculate and save').click().run(timeout=30)
    assert not at.exception and at.session_state['workbook_result']['report']['results'][0]['value']==1200


def test_existing_session_receives_additive_library_migration(fresh_app,reference_ui):
    at=fresh_app
    conn=at.session_state['conn'];conn.execute('DROP TABLE project_calculation_packages');conn.commit()
    del at.session_state['_schema_token']
    at=open_page(at)
    assert not at.exception
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='project_calculation_packages'").fetchone()
    assert conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==1


def test_saved_legacy_package_opens_and_saves_with_upgraded_identity(fresh_app,reference_ui):
    from tests.test_interactive_packages import legacy_package
    from workbooks.interactive import encode_package,decode_package
    at=fresh_app
    next(b for b in at.button if b.label=='Create project').click().run(timeout=30)
    p=legacy_package();old_hash=p['package_sha256'];canonical=decode_package(encode_package(p))
    conn=at.session_state['conn']
    conn.execute('INSERT INTO project_calculation_packages(project_id,package_sha256,title,package_json) VALUES (?,?,?,?)',
                 (1,old_hash,p['title'],encode_package(p).decode('utf-8')));conn.commit()
    at.session_state['calculation_picker_1']=old_hash
    at.session_state['calculation_draft_1:1:'+old_hash+':Flow and duration']={'G10':3.,'G11':20.}
    at.sidebar.radio[0].set_value('Calculation Sheets').run(timeout=30)
    assert not at.exception and not at.error
    assert next(n for n in at.number_input if n.label=='Flow rate (L/s)').value==3
    next(b for b in at.button if b.label=='Calculate and save').click().run(timeout=30)
    assert not at.exception
    row=conn.execute("SELECT inputs_json,intermediate_json,target_id FROM calculations WHERE calc_type='reference_workbook_scenario'").fetchone()
    assert json.loads(row['inputs_json'])['package_sha256']==canonical['package_sha256']
    assert json.loads(row['intermediate_json'])['results'][0]['value']==3600
    assert row['target_id'].startswith(canonical['package_sha256'])
