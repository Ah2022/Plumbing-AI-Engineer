"""Synthetic transaction/API contracts; these tests are NOT real-model acceptance."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from bim.mapping import revit_inventory,initial_mapping,snapshot
from bim.round_trip import prepare_analysis,verify_round_trip,run_in_revit
from bim.revit_handoff import apply_handoff,checksum
from tests.test_revit_handoff import Document,DB,extract
from tests.test_review_workflow import project


def inputs():
    before=extract();inv=revit_inventory(before);rows=initial_mapping(inv)
    rows[0].update(service='cold_water',nominal_mm=25.,internal_mm=20.,design_flow_lps=.2,elevation_m=0.,
        engineering_reviewer='Synthetic reviewer',evidence_reference='Synthetic bore/flow')
    return before,rows


def reextract(before,doc):
    after=deepcopy(before);after['extracted_at']='2026-10-28T01:00:00Z'
    after['pipes'][0]['parameters']={k:p.value for k,p in doc.parameters.items()}
    return after


def test_import_calculate_write_reextract_without_manual_database_edits(project):
    conn,pid=project;before,rows=inputs()
    prepared=prepare_analysis(conn,pid,before,rows,[],'Synthetic reviewer','Synthetic R1',1.,'Synthetic velocity criterion')
    doc=Document();packet=prepared['handoff']
    assert apply_handoff(doc,DB,packet,commit=True)['status']=='COMMITTED'
    verified=verify_round_trip(before,reextract(before,doc),packet)
    assert verified['status']=='PASS' and verified['verified_elements']==1
    assert doc.parameters['PLM_Review_Status'].value=='REVIEW_REQUIRED'
    assert doc.parameters['PLM_Code_Status'].value!='PASS'
    result=conn.execute("SELECT * FROM calculations WHERE calc_type='bim_pipe_velocity'").fetchone()
    assert result['review_status']=='REVIEW_REQUIRED' and result['result_value']==pytest.approx(.6366197723675814,abs=5e-5)


@pytest.mark.parametrize('change',['status','value','identity','geometry','missing_parameter'])
def test_round_trip_detects_unstable_identity_and_result_fields(project,change):
    conn,pid=project;before,rows=inputs();packet=prepare_analysis(conn,pid,before,rows,[],'S','R1',1.,'S')['handoff']
    doc=Document();apply_handoff(doc,DB,packet,commit=True);after=reextract(before,doc)
    if change=='status':after['pipes'][0]['parameters']['PLM_Review_Status']='VERIFIED'
    elif change=='value':after['pipes'][0]['parameters']['PLM_Result_Value']+=1
    elif change=='identity':after['pipes'][0]['revit_unique_id']='replaced'
    elif change=='geometry':after['pipes'][0]['length_m']+=1
    else:del after['pipes'][0]['parameters']['PLM_Result_Available']
    assert verify_round_trip(before,after,packet)['status']=='FAIL'


def test_tampered_handoff_or_foreign_source_is_rejected(project):
    conn,pid=project;before,rows=inputs();p=prepare_analysis(conn,pid,before,rows,[],'S','R1',1.,'S')['handoff']
    bad=deepcopy(p);bad['payload']['updates'][0]['parameters']['PLM_Result_Value']=999
    with pytest.raises(ValueError,match='checksum'):verify_round_trip(before,before,bad)
    before['extracted_at']='different source'
    with pytest.raises(ValueError,match='bound'):verify_round_trip(before,before,p)


def test_native_harness_default_rolls_back_and_committed_path_reextracts(project,monkeypatch):
    conn,pid=project;before,rows=inputs();doc=Document();doc.Application=NS(VersionNumber='SYNTHETIC API')
    reviewed=snapshot(revit_inventory(before),rows,[],'Synthetic reviewer','Synthetic R1')
    import bim.revit_extract as adapter
    calls=[]
    def capture(*args):
        calls.append(1)
        return deepcopy(before) if len(calls)%2 else reextract(before,doc)
    monkeypatch.setattr(adapter,'extract_document',capture)
    record=run_in_revit(doc,DB,conn,pid,reviewed,lambda x:x,1.,'Synthetic velocity criterion')
    assert record['write']['status']=='DRY_RUN_ROLLED_BACK' and record['verification']['status']=='NOT_EXECUTED'
    record=run_in_revit(doc,DB,conn,pid,reviewed,lambda x:x,1.,'Synthetic velocity criterion',commit=True)
    assert record['verification']['status']=='PASS' and len(calls)==4


def test_incomplete_or_unreviewed_inputs_stop_before_import(project):
    conn,pid=project;before,rows=inputs();rows[0]['engineering_reviewer']=''
    with pytest.raises(ValueError,match='reviewer'):prepare_analysis(conn,pid,before,rows,[],'S','R1',1.,'S')
    assert conn.execute('SELECT count(*) FROM revit_model_imports').fetchone()[0]==0
    rows[0]['engineering_reviewer']='S';rows[0]['internal_mm']=None
    with pytest.raises(ValueError,match='bore'):prepare_analysis(conn,pid,before,rows,[],'S','R1',1.,'S')


def test_criterion_uses_unrounded_velocity(project):
    conn,pid=project;before,rows=inputs()
    packet=prepare_analysis(conn,pid,before,rows,[],'S','R1',.63661,'Synthetic rounding boundary')['handoff']
    assert packet['payload']['updates'][0]['parameters']['PLM_Technical_Status']=='FAIL'


def test_source_change_between_review_and_native_run_stops_before_calculation(project,monkeypatch):
    conn,pid=project;before,rows=inputs();doc=Document();doc.Application=NS(VersionNumber='SYNTHETIC')
    reviewed=snapshot(revit_inventory(before),rows,[],'S','R1');before['pipes'][0]['nominal_diameter_mm']=32.
    import bim.revit_extract as adapter
    monkeypatch.setattr(adapter,'extract_document',lambda *args:before)
    with pytest.raises(ValueError,match='changed since mapping'):run_in_revit(doc,DB,conn,pid,reviewed,lambda x:x,1.,'S',commit=True)
    assert conn.execute('SELECT count(*) FROM calculations').fetchone()[0]==0 and doc.started==0
