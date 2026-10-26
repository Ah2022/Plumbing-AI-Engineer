"""Independent synthetic spreadsheet semantics and failure-isolation benchmarks."""
from io import BytesIO
from zipfile import ZipFile
import json
import pytest

from workbooks.reader import read_workbook
from workbooks.formulas import Evaluator,FormulaError,UnsupportedFormula
from workbooks.library import run_scenario,describe,bases,install_archives,load_source,catalog


def book(formula='A1*B1',extra=None):
    cells={'A1':dict(value=3,formula=None,error=False),'B1':dict(value=4,formula=None,error=False),
           'C1':dict(value=999,formula=formula,error=False)}
    cells.update(extra or {})
    return dict(sha256='synthetic',names={},sheets={'Calc':dict(cells=cells,state='visible')})


@pytest.mark.parametrize('formula,expected',[
    ('A1*B1+2^3',20),('IF(A1=3,12,1/0)',12),('IF(FALSE,1/0,7)',7),
    ('SUM(A1:B1)',7),('MAX(A1:B1)',4),('ROUND(2.5,0)',3),('ROUND(-2.5,0)',-3),
    ('ROUNDUP(-2.01,0)',-3),('EVEN(3.1)',4),('EVEN(-3.1)',-4),
    ('SQRT(9)',3),('SIN(RADIANS(90))',1),('COS(0)',1),('ABS(-7)',7),
    ('INDEX(A1:B1,2)',4),('MATCH(4,A1:B1,0)',2),('LOOKUP(3.5,A1:B1,A1:B1)',3),
    ('HLOOKUP(3,A1:B1,1,FALSE)',3),('VLOOKUP(3,A1:B1,2,FALSE)',4),
    ('ISNUMBER(MATCH(99,A1:B1,0))',False),('COLUMN()',3),
    ('INDIRECT("A"&1)+B1',7),('SUM(INDIRECT("A1"):INDIRECT("B1"))',7),
    ('CHAR(65)&"2"','A2'),('IF("ipc"="IPC",8,0)',8),('10%',.1),
])
def test_supported_formulas_against_independent_values(formula,expected):
    actual=Evaluator(book(formula)).cell('Calc','C1')
    if isinstance(expected,(int,float)):assert actual==pytest.approx(expected)
    else:assert actual==expected


def test_changed_input_recalculates_and_never_uses_cache():
    r=run_scenario(book(),['Calc!C1'],{'Calc!A1':5})
    assert r['results'][0]['value']==20
    assert r['review_status']=='REVIEW_REQUIRED' and r['results'][0]['status']=='CALCULATED_NOT_APPROVED'
    assert r['trace']['Calc!C1']['formula']=='A1*B1'
    assert r['input_sha256']!=run_scenario(book(),['Calc!C1'])['input_sha256']


@pytest.mark.parametrize('formula', ['WEIGHT2SUM(A1:B1)','INDIRECT("[1]Other!A1")','DDE("cmd")'])
def test_unsupported_formula_never_returns_plausible_saved_value(formula):
    r=run_scenario(book(formula),['Calc!C1'])
    assert r['results'][0]['value'] is None and r['results'][0]['status']=='NOT_EVALUATED'


def test_unsupported_formula_is_not_masked_by_isnumber():
    with pytest.raises(UnsupportedFormula):Evaluator(book('ISNUMBER(WEIGHT2SUM(A1))')).cell('Calc','C1')


def test_circular_references_and_broken_names_are_explicit():
    assert run_scenario(book('C1+1'),['Calc!C1'])['results'][0]['status']=='MISSING_DATA'
    b=book('broken');b['names']['!BROKEN']='#REF!'
    assert run_scenario(b,['Calc!C1'])['results'][0]['status']=='MISSING_DATA'


def test_approximate_lookup_requires_sorted_vector_and_no_high_end_clamping():
    b=book('MATCH(3.5,A1:B1,1)');b['sheets']['Calc']['cells']['A1']['value']=5
    with pytest.raises(FormulaError,match='not sorted'):Evaluator(b).cell('Calc','C1')
    assert run_scenario(book('INDEX(A1:B1,MATCH(99,A1:B1,1)+1)'),['Calc!C1'])['results'][0]['status']=='MISSING_DATA'


@pytest.mark.parametrize('overrides',[{'Calc!C1':5},{'Calc!Z999':5},{'Calc!A1':float('nan')},{'Calc!A1':[]},{'Calc!A1':1,"'Calc'!A1":2}])
def test_invalid_overrides_are_rejected(overrides):
    with pytest.raises(ValueError):run_scenario(book(),['Calc!C1'],overrides)


def test_cell_alias_override_is_normalized():
    assert run_scenario(book(),['Calc!C1'],{"'Calc'!$A$1":5})['results'][0]['value']==20


def test_references_cannot_change_code_adoption():
    b=book('A1');b.update(functions={},macros=True,external_links=1,cached_errors=[])
    b['sheets']['Calc']['cells']['A1']['value']='From NSPC-2009 Ch.16'
    d=describe(b,'Septic.xlsm')
    assert d['primary_bases']==['NSPC'] and d['verification_status']=='UNVERIFIED_REFERENCE'
    assert bases('From 2011 ASHRAE Handbook Table 10')==['ASHRAE']


def package():
    b=BytesIO()
    with ZipFile(b,'w') as z:
        z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Calc" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><v>3</v></c><c r="B1"><f t="shared" si="0" ref="B1:B2">A1*2</f><v>6</v></c></row><row r="2"><c r="A2"><v>4</v></c><c r="B2"><f t="shared" si="0"/><v>8</v></c></row></sheetData></worksheet>')
        z.writestr('xl/vbaProject.bin',b'NOT EXECUTABLE TEST FIXTURE')
    return b.getvalue()


def test_reader_expands_shared_formula_without_running_macros():
    b=read_workbook(package())
    assert b['macros'] and b['sheets']['Calc']['cells']['B2']['formula']=='A2*2'
    assert run_scenario(b,['Calc!B2'])['results'][0]['value']==8


def test_archive_import_ignores_locks_uses_safe_paths_and_verifies_hash(tmp_path):
    archive=tmp_path/'supplied.zip';dest=tmp_path/'sources';cp=tmp_path/'catalog.json'
    with ZipFile(archive,'w') as z:
        z.writestr('../../Outside.xlsm',package());z.writestr('~$Locked.xlsm',b'LOCK');z.writestr('desktop.ini',b'IGNORE')
    result=install_archives([archive],directory=dest,catalog_path=cp)
    assert result['imported']==1 and len(list(dest.glob('*.xlsm')))==1
    assert not (tmp_path.parent/'Outside.xlsm').exists()
    entry=catalog(cp)['workbooks'][0]
    assert load_source(entry,dest)['sha256']==entry['sha256']
    next(dest.glob('*.xlsm')).write_bytes(b'CHANGED')
    with pytest.raises(ValueError,match='fingerprint'):load_source(entry,dest)


def test_all_supplied_metadata_is_registered():
    entries=catalog()['workbooks']
    assert len(entries)==48
    assert len({e['sha256'] for e in entries})==48
    assert all(e['verification_status']=='UNVERIFIED_REFERENCE' for e in entries)
    assert all(not PathLike in json.dumps(entries) for PathLike in ['C:\\Users\\','value_num'])
