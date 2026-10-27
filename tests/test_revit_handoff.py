"""Synthetic API contract tests; no live Revit model is modified."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from app.db_helpers import save_calculation
from bim.exchange import import_revit_extract, export_results_for_revit
from bim.revit_handoff import (build_handoff,preflight_handoff,apply_handoff,checksum,
                              TEXT_FIELDS,NUMBER_FIELDS,FLAG_FIELDS)
from calculations.hot_water import heater_capacity
from models import CalculationResult
from reports.review_workflow import propose_override
from tests.test_review_workflow import project


def extract():
    return dict(schema_version='1.0',units='SI',revit_model_id='project:test.rvt',revit_model_name='Synthetic model',
        extracted_at='2026-10-27T00:00:00Z',pipes=[dict(revit_element_id='1',revit_unique_id='uid-1',
        system='cold_water',length_m=1.,nominal_diameter_mm=25.)],fixtures=[],tanks=[],pumps=[])


def test_export_uses_governing_failure_values_and_blocks_override(project):
    conn,pid=project; import_revit_extract(conn,pid,extract())
    pipe=conn.execute('SELECT pipe_id,revit_model_key FROM pipes').fetchone()
    fail=CalculationResult('FAIL','first_check','Synthetic',{}, {},2,'m',status='FAIL')
    passing=CalculationResult('PASS','second_check','Synthetic',{}, {},999,'m',status='PASS')
    for result in (fail,passing):
        save_calculation(conn,pid,result,target_type='pipe',target_id=pipe['pipe_id'])
    exported=export_results_for_revit(conn,pid,pipe['revit_model_key'])['results']['1']
    assert exported['status']=='FAIL' and exported['result_value']==2 and exported['calc_id']=='FAIL'
    packet=build_handoff(conn,pid,pipe['revit_model_key'])
    assert packet['payload']['ready_for_preflight']
    assert packet['payload']['updates'][0]['parameters']['PLM_Required_Available']==0
    assert packet['payload']['updates'][0]['parameters']['PLM_Required_Value']==0
    propose_override(conn,pid,'FAIL','result_value',4,'m','Synthetic reviewer','Evidence')
    assert not build_handoff(conn,pid,pipe['revit_model_key'])['payload']['ready_for_preflight']


def packet():
    params={name:'Synthetic' for name in TEXT_FIELDS}
    params.update({name:10. for name in NUMBER_FIELDS})
    params.update({name:1 for name in FLAG_FIELDS})
    params.update(PLM_Code_Status='WARNING',PLM_Technical_Status='PASS',PLM_Review_Status='REVIEW_REQUIRED',PLM_Source_SHA256='0'*64)
    params['PLM_Required_Value']=0.; params['PLM_Required_Available']=0
    payload=dict(schema_version='revit-handoff-1',model_identity='project:test.rvt',source_sha256='0'*64,blockers=[],
        updates=[dict(element_id='1',unique_id='uid-1',source=dict(length_m=1.,nominal_diameter_mm=25.),parameters=params)])
    return dict(payload=payload,sha256=checksum(payload))


class Parameter:
    def __init__(self,name):
        self.StorageType='String' if name in TEXT_FIELDS else 'Integer' if name in FLAG_FIELDS else 'Double'
        self.IsReadOnly=False; self.value='old' if self.StorageType=='String' else 99
        self.Definition=NS(GetDataType=lambda:'Number')
        self.fail=False
    def Set(self,value):
        if self.fail:
            return False
        self.value=value; return True


class Document:
    IsModelInCloud=False
    PathName='test.rvt'
    ProjectInformation=NS(UniqueId='project')
    def __init__(self):
        self.parameters={name:Parameter(name) for name in TEXT_FIELDS+NUMBER_FIELDS+FLAG_FIELDS}
        self.started=0; self.length_ft=1/.3048
        self.element=NS(UniqueId='uid-1',Id=NS(Value=1),LookupParameter=lambda name:self.parameters.get(name),
            get_Parameter=lambda name:NS(HasValue=True,AsDouble=lambda:25/304.8))
        self.element.Location=NS(Curve=NS(Length=self.length_ft,
            GetEndPoint=lambda i:NS(X=self.length_ft*i,Y=0.,Z=0.)))
    def GetElement(self,identity):
        return self.element if identity=='uid-1' else None


class Transaction:
    def __init__(self,doc,name):
        self.doc=doc; self.state='Uninitialized'
    def Start(self):
        self.doc.started+=1; self.before={k:p.value for k,p in self.doc.parameters.items()}; self.state='Started'; return self.state
    def Commit(self):
        self.state='Committed'; return self.state
    def RollBack(self):
        for k,value in self.before.items(): self.doc.parameters[k].value=value
        self.state='RolledBack'; return self.state
    def GetStatus(self): return self.state
    def Dispose(self): pass


DB=NS(StorageType=NS(String='String',Integer='Integer',Double='Double'),SpecTypeId=NS(Number='Number'),
    BuiltInParameter=NS(RBS_PIPE_DIAMETER_PARAM='diameter'),UnitTypeId=NS(Meters='m',Millimeters='mm'),
    UnitUtils=NS(ConvertFromInternalUnits=lambda v,unit:v*(.3048 if unit=='m' else 304.8)),
    Transaction=Transaction,TransactionStatus=NS(Started='Started',Committed='Committed',RolledBack='RolledBack'))


def test_default_dry_run_rolls_back_every_parameter():
    doc=Document(); before={k:p.value for k,p in doc.parameters.items()}
    result=apply_handoff(doc,DB,packet())
    assert result['status']=='DRY_RUN_ROLLED_BACK' and result['written']==0
    assert before=={k:p.value for k,p in doc.parameters.items()}


def test_explicit_commit_sets_availability_flags_instead_of_retaining_stale_numbers():
    doc=Document(); result=apply_handoff(doc,DB,packet(),commit=True)
    assert result['status']=='COMMITTED'
    assert doc.parameters['PLM_Required_Available'].value==0 and doc.parameters['PLM_Required_Value'].value==0.
    assert doc.parameters['PLM_Review_Status'].value=='REVIEW_REQUIRED'


def test_parameter_failure_rolls_back_earlier_writes():
    doc=Document(); before={k:p.value for k,p in doc.parameters.items()}
    doc.parameters['PLM_Result_Value'].fail=True
    with pytest.raises(ValueError,match='rolled back'):
        apply_handoff(doc,DB,packet(),commit=True)
    assert before=={k:p.value for k,p in doc.parameters.items()}


def test_wrong_model_or_changed_source_blocks_writes():
    doc=Document(); doc.ProjectInformation=NS(UniqueId='wrong model')
    with pytest.raises(ValueError,match='different model'):
        apply_handoff(doc,DB,packet(),commit=True)
    assert doc.started==0
    doc=Document(); doc.element.Location.Curve.Length+=1
    assert apply_handoff(doc,DB,packet(),commit=True)['status']=='BLOCKED' and doc.started==0


def test_missing_parameter_or_wrong_physical_spec_blocks_every_write():
    doc=Document(); del doc.parameters['PLM_Review_Status']
    assert apply_handoff(doc,DB,packet(),commit=True)['status']=='BLOCKED' and doc.started==0
    doc=Document(); doc.parameters['PLM_Result_Value'].Definition=NS(GetDataType=lambda:'Length')
    assert not preflight_handoff(doc,DB,packet())['can_write']


def test_tampered_packet_and_native_dimension_parameter_are_rejected():
    doc=Document(); p=packet(); p['payload']['updates'][0]['parameters']['Diameter']=100
    with pytest.raises(ValueError,match='checksum'):
        preflight_handoff(doc,DB,p)
    p['sha256']=checksum(p['payload'])
    with pytest.raises(ValueError,match='non-PLM'):
        preflight_handoff(doc,DB,p)


def test_unverified_code_pass_cannot_be_written():
    p=packet(); p['payload']['updates'][0]['parameters']['PLM_Code_Status']='PASS'; p['sha256']=checksum(p['payload'])
    with pytest.raises(ValueError,match='Unverified'):
        preflight_handoff(Document(),DB,p)
