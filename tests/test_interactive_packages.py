from copy import deepcopy
from io import BytesIO
import json
from zipfile import ZipFile,ZIP_DEFLATED
import pytest

from workbooks.demo import demo_package
from workbooks.interactive import (decode_package,encode_package,build_package,bundle,import_bytes,run_package,
                                  install_project_packages,project_packages,digest,choices_for,compile_forms,FORM_COMPILER_VERSION)
from database.db import init_db,get_connection
from tests.test_workbooks import package as excel_package


def test_portable_form_recalculates_without_excel(monkeypatch):
    p=decode_package(encode_package(demo_package()))
    import workbooks.interactive as api
    monkeypatch.setattr(api,'read_workbook',lambda *a:(_ for _ in ()).throw(AssertionError('Excel runtime must not be used')))
    r=run_package(p,'Flow and duration',{'G10':3,'G11':20})
    assert r['results'][0]['value']==3600
    assert r['review_status']=='REVIEW_REQUIRED' and r['package_sha256']==p['package_sha256']
    assert [f['label'] for f in p['forms']['Flow and duration']['inputs']]==['Flow rate (L/s)','Duration (minutes)']


def test_package_round_trip_and_zip_reimport_are_stable():
    p=demo_package();q=decode_package(encode_package(p))
    assert decode_package(encode_package(q))==q
    imported=import_bytes(bundle([q]),'library.zip')
    assert imported[0]['package_sha256']==p['package_sha256']


def test_uploaded_excel_is_converted_without_executing_vba():
    p=import_bytes(excel_package(),'supplied.xlsm')[0]
    assert p['workbook']['macros']
    assert run_package(p,'Calc',{})['results'][0]['value']==6


def test_changed_input_is_bound_to_the_result_identity():
    p=demo_package()
    assert run_package(p,'Flow and duration',{'G10':2,'G11':10})['input_sha256']!=run_package(p,'Flow and duration',{'G10':3,'G11':10})['input_sha256']


def test_modified_calculation_requires_new_checksum():
    p=demo_package();p['workbook']['sheets']['Flow and duration']['cells']['G10']['value']=500
    with pytest.raises(ValueError,match='checksum'):decode_package(encode_package(p))


def test_package_ui_cannot_insert_unrelated_editable_controls():
    p=demo_package();p['forms']['Flow and duration']['inputs'][0]['cell']='G13'
    p['package_sha256']=digest({k:v for k,v in p.items() if k!='package_sha256'})
    with pytest.raises(ValueError,match='form definitions'):decode_package(encode_package(p))


@pytest.mark.parametrize('value',[float('nan'),float('inf'),[],{'value':3}])
def test_invalid_native_input_is_rejected(value):
    with pytest.raises(ValueError):run_package(demo_package(),'Flow and duration',{'G10':value})


def test_formula_output_cannot_be_overridden():
    with pytest.raises(ValueError,match='input fields'):run_package(demo_package(),'Flow and duration',{'G13':42})


def test_unknown_function_has_no_saved_cache_fallback():
    p=demo_package();b=deepcopy(p['workbook']);b['sheets']['Flow and duration']['cells']['G13']['formula']='WEIGHT2SUM(G10)'
    p=build_package(b,'Unknown.xlsx')
    r=run_package(p,'Flow and duration',{})
    assert r['results'][0]['value'] is None and r['results'][0]['status']=='NOT_EVALUATED'


def test_dropdown_values_resolve_from_the_original_validation():
    p=demo_package();field=p['forms']['Flow and duration']['inputs'][0]
    field['validation']={'type':'list','formula1':'"25%,50%,100%"'}
    assert choices_for(p['workbook'],'Flow and duration',field)==[.25,.5,1.]


def test_zip_lock_files_are_not_imported():
    b=BytesIO()
    with ZipFile(b,'w',ZIP_DEFLATED) as z:
        z.writestr('~$temp.xlsm',b'not a workbook');z.writestr('Library/example.plmcalc',encode_package(demo_package()))
    assert len(import_bytes(b.getvalue(),'import.zip'))==1


def test_import_is_project_scoped_and_survives_database_reopen(tmp_path):
    path=tmp_path/'project.db';conn=init_db(path)
    conn.execute("INSERT INTO codes(code_id,code_name) VALUES ('TEST','Synthetic')")
    for pid in (1,2):conn.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES (?,?,?,?)",(pid,'Synthetic','Office','TEST'))
    conn.commit();p=demo_package()
    install_project_packages(conn,1,[p]);install_project_packages(conn,1,[p])
    assert not project_packages(conn,2) and len(project_packages(conn,1))==1
    conn.close();conn=get_connection(path)
    try:assert run_package(project_packages(conn,1)[0],'Flow and duration',{})['results'][0]['value']==1200
    finally:conn.close()


@pytest.mark.parametrize('mutation',[
    lambda p:p.update(workbook=[]),
    lambda p:p.update(metadata='bad'),
    lambda p:p['workbook']['sheets']['Flow and duration'].update(merges=['A:A']),
    lambda p:p['workbook']['sheets']['Flow and duration']['cells']['G10'].update(value=[]),
    lambda p:p['workbook']['sheets']['Flow and duration']['cells']['G10'].update(validation={'type':'list','formula1':{}}),
])
def test_malformed_resigned_package_is_rejected_cleanly(mutation):
    p=demo_package();mutation(p);p['package_sha256']=digest({k:v for k,v in p.items() if k!='package_sha256'})
    with pytest.raises(ValueError):decode_package(encode_package(p))


def test_formula_driven_field_labels_and_geometry_remain_interactive():
    p=demo_package();book=deepcopy(p['workbook']);cells=book['sheets']['Flow and duration']['cells']
    cells['A9']=dict(value='Shape',formula=None,error=False)
    cells['G9']=dict(value='Rectangular',formula=None,error=False,validation={'type':'list','formula1':'"Rectangular,Circular"'})
    cells['A10']=dict(value='Length (m)',formula='IF(G9="Circular","Diameter (m)","Length (m)")',error=False)
    cells['G13']['formula']='IF(G9="Circular",3.14*G10^2/4,G10^2)'
    q=build_package(book,'Geometry example.xlsx');form=q['forms']['Flow and duration']
    assert next(f for f in form['inputs'] if f['cell']=='G10')['label_cell']=='A10'
    assert run_package(q,'Flow and duration',{'G9':'Circular','G10':2})['results'][0]['value']==pytest.approx(3.14)


def test_repeated_schedule_labels_include_the_column_heading():
    p=demo_package();b=deepcopy(p['workbook']);c=b['sheets']['Flow and duration']['cells']
    c['A9']=dict(value='Department',formula=None,error=False)
    c['G9']=dict(value='Oxygen quantity',formula=None,error=False)
    c['H9']=dict(value='Medical air quantity',formula=None,error=False)
    c['A10']=dict(value='Synthetic ward',formula=None,error=False)
    c['H10']=dict(value=4.,formula=None,error=False)
    c['G13']['formula']='G10+H10'
    q=build_package(b,'Schedule example.xlsx');fields=q['forms']['Flow and duration']['inputs']
    assert 'Oxygen quantity' in next(f for f in fields if f['cell']=='G10')['label']
    assert 'Medical air quantity' in next(f for f in fields if f['cell']=='H10')['label']


def legacy_package():
    p=demo_package();p.pop('form_compiler_version')
    p['forms']['Flow and duration']['inputs'][0]['label']='Older layout label'
    p['package_sha256']=digest({k:v for k,v in p.items() if k!='package_sha256'})
    return p


def test_older_layout_upgrades_without_changing_source_data():
    old=legacy_package();source=deepcopy(old['workbook'])
    upgraded=decode_package(encode_package(old))
    assert upgraded['form_compiler_version']==FORM_COMPILER_VERSION
    assert upgraded['upgraded_from_package']==old['package_sha256']
    assert upgraded['workbook']==source
    assert upgraded['forms']['Flow and duration']['inputs'][0]['label']=='Flow rate (L/s)'
    assert decode_package(encode_package(upgraded))==upgraded
    assert run_package(upgraded,'Flow and duration',{'G10':3,'G11':20})['results'][0]['value']==3600


def test_older_layout_checksum_still_prevents_modified_calculations():
    p=legacy_package();p['workbook']['sheets']['Flow and duration']['cells']['G10']['value']=500
    with pytest.raises(ValueError,match='checksum'):decode_package(encode_package(p))


def test_older_layout_cannot_make_formula_outputs_editable():
    p=legacy_package();p['forms']['Flow and duration']['inputs'][0]['cell']='G13'
    p['package_sha256']=digest({k:v for k,v in p.items() if k!='package_sha256'})
    with pytest.raises(ValueError,match='form definitions'):decode_package(encode_package(p))


def test_compilation_is_idempotent_with_blank_referenced_inputs():
    b=demo_package()['workbook'];c=b['sheets']['Flow and duration']['cells']
    c['G13']['formula']='G10*G11*60+G15+H15'
    c['A15']=dict(value='Additional allowance (litres)',formula=None,error=False)
    first=compile_forms(b);second=compile_forms(b)
    assert first==second and c['G15']['value'] is None and c['H15']['value'] is None


def test_legacy_install_uses_upgraded_identity(tmp_path):
    c=init_db(tmp_path/'legacy.db')
    try:
        c.execute("INSERT INTO codes(code_id,code_name) VALUES ('TEST','Synthetic')")
        c.execute("INSERT INTO projects(project_id,project_name,building_type,code_id) VALUES (1,'Synthetic','Office','TEST')");c.commit()
        old=legacy_package();install_project_packages(c,1,[old])
        saved=project_packages(c,1)[0]
        assert saved['package_sha256']!=old['package_sha256']
        assert c.execute('SELECT package_sha256 FROM project_calculation_packages').fetchone()[0]==saved['package_sha256']
    finally:c.close()


def test_package_identity_is_stable_across_process_hash_seeds():
    import subprocess,sys,os
    from pathlib import Path
    book=demo_package()['workbook'];cells=book['sheets']['Flow and duration']['cells']
    cells['G13']['formula']='G10*G11*60+G15+H15'
    cells['A15']=dict(value='Allowance (litres)',formula=None,error=False)
    code="import json,sys; from workbooks.interactive import build_package; print(build_package(json.load(sys.stdin),'Synthetic.xlsx')['package_sha256'])"
    hashes=[]
    for seed in ('1','42'):
        r=subprocess.run([sys.executable,'-c',code],input=json.dumps(book),text=True,capture_output=True,
                         env=dict(os.environ,PYTHONHASHSEED=seed),cwd=Path(__file__).resolve().parents[1],timeout=30,check=True)
        hashes.append(r.stdout.strip())
    assert hashes[0]==hashes[1]
