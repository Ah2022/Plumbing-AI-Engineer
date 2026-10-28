"""Injected native-API contracts; synthetic objects do not establish real-model acceptance."""
from types import SimpleNamespace as NS
from copy import deepcopy
import pytest
from bim.revit_extract import extract_document,physical_ports
from bim.schemas import validate_extract_payload
from bim.mapping import revit_inventory


class Parameter:
    def __init__(self,value,storage='String'):
        self.value=value;self.StorageType=storage;self.HasValue=True
    def AsString(self):return self.value
    def AsValueString(self):return self.value
    def AsDouble(self):return self.value


class Line:
    Length=10.
    def GetEndPoint(self,i):return NS(X=i*10.,Y=0.,Z=10.)


class Element:
    def __init__(self,i,kind):
        self.Id=NS(Value=i);self.UniqueId='uid-'+str(i);self.Name='Synthetic '+kind
        self.kind=kind;self.Location=NS(Curve=Line()) if kind=='pipe' else NS(Point=NS(X=0.,Y=0.,Z=10.))
        self.MEPSystem=NS(Name='Synthetic CW')
        self.params={'PLM_Equipment_Class':Parameter(kind),'PLM_Tank_Type':Parameter('domestic')}
        self.port=NS(Id=1,Owner=self,Domain='DomainPiping',ConnectorType='End',Direction='In',Origin=NS(X=0.,Y=0.,Z=10.),AllRefs=[],MEPSystem=self.MEPSystem)
        self.port.IsConnectedTo=lambda other:other in self.port.AllRefs
        manager=NS(Connectors=[self.port])
        if kind=='pipe':self.ConnectorManager=manager
        else:self.MEPModel=NS(ConnectorManager=manager)
    def GetTypeId(self):return 'type-'+self.UniqueId
    def GetType(self):return NS(Name='SyntheticNative'+self.kind)
    def LookupParameter(self,name):return self.params.get(name)
    def get_Parameter(self,token):
        return {'diameter':Parameter(1/12,'Double'),'inner':Parameter(.07,'Double'),
            'flow':Parameter(.01,'Double'),'classification':Parameter('DomesticColdWater')}.get(token)


def api():
    elements=[Element(i,kind) for i,kind in enumerate(('pipe','fixture','tank','pump','valve','fitting'),1)]
    elements[0].port.AllRefs=[elements[1].port]
    elements[1].port.AllRefs=[elements[0].port]
    categories=dict(OST_PipeCurves=[elements[0]],OST_PlumbingFixtures=[elements[1]],OST_MechanicalEquipment=elements[2:4],
        OST_PipeAccessory=[elements[4]],OST_PipeFitting=[elements[5]],OST_GenericModel=[])
    class Collector:
        def __init__(self,doc):pass
        def OfCategory(self,category):self.rows=categories[category];return self
        def WhereElementIsNotElementType(self):return self.rows
    class Doc:
        IsFamilyDocument=False;IsModelInCloud=False;PathName='synthetic.rvt';Title='Synthetic native API';IsModified=False
        ProjectInformation=NS(UniqueId='synthetic-project');Application=NS(VersionNumber='2024')
        def GetElement(self,identity):return NS(UniqueId=identity,Name='Synthetic type',Family=NS(Name='Synthetic family'))
    DB=NS(FilteredElementCollector=Collector,BuiltInCategory=NS(**{k:k for k in categories}),Line=Line,
        BuiltInParameter=NS(RBS_PIPE_DIAMETER_PARAM='diameter',RBS_PIPE_INNER_DIAM_PARAM='inner',RBS_PIPE_FLOW_PARAM='flow',RBS_SYSTEM_CLASSIFICATION_PARAM='classification'),
        UnitTypeId=NS(Meters='m',Millimeters='mm',LitersPerSecond='LPS'),
        UnitUtils=NS(ConvertFromInternalUnits=lambda x,u:x*{'m':.3048,'mm':304.8,'LPS':28.316846592}[u]),
        ConnectorType=NS(Logical='Logical'),SpecTypeId=NS(Number='Number'),
        Document=NS(GetDocumentVersion=lambda d:NS(VersionGUID='SYNTHETIC',NumberOfSaves=1)))
    return Doc(),DB,elements


def test_all_equipment_families_piping_ports_units_and_revision_are_extracted():
    doc,DB,elements=api()
    payload=extract_document(doc,DB,lambda label:'cold_water' if label=='DomesticColdWater' else None)
    assert validate_extract_payload(payload)==[]
    assert all(len(payload[g])==1 for g in ('pipes','fixtures','tanks','pumps','valves'))
    assert len(payload['inventory']['objects'])==6 and len(payload['inventory']['connections'])==1
    pipe=next(o for o in payload['inventory']['objects'] if o['kind']=='pipe')
    assert pipe['nominal_mm']==pytest.approx(25.4) and pipe['internal_mm']==pytest.approx(21.336)
    assert pipe['flow_lps']==pytest.approx(.28316846592) and pipe['elevation_m']==pytest.approx(3.048)
    assert payload['model_revision']['number_of_saves']==1
    assert payload['fixtures'][0]['family']=='Synthetic family'
    assert revit_inventory(payload)['source_sha256']


def test_unknown_equipment_is_not_guessed_from_family_name():
    doc,DB,elements=api();elements[2].params={};elements[2].Name='Huge domestic water tank'
    payload=extract_document(doc,DB,lambda _:'cold_water')
    assert payload['tanks']==[]
    assert not any(o['source_id']==elements[2].UniqueId for o in payload['inventory']['objects'])


def test_partition_keeps_external_port_references_and_unknown_pipe_service():
    doc,DB,elements=api();payload=extract_document(doc,DB,lambda _:None,{'1'})
    assert payload['pipes']==[] and len(payload['inventory']['objects'])==1
    assert len(payload['inventory']['connections'])==1 and payload['skipped']


def test_logical_connectors_never_become_physical_edges():
    doc,DB,elements=api();other=NS(Owner=elements[1],Domain='DomainPiping',ConnectorType='Logical')
    elements[0].port.AllRefs=[other]
    ports,links,issues=physical_ports(elements[0],DB)
    assert len(ports)==1 and not links and not issues


def test_native_inventory_duplicate_ids_or_nonfinite_coordinates_are_rejected():
    doc,DB,_=api();payload=extract_document(doc,DB,lambda _:'cold_water')
    bad=deepcopy(payload);bad['inventory']['objects'].append(deepcopy(bad['inventory']['objects'][0]))
    assert any('Duplicate' in e for e in validate_extract_payload(bad))
    bad=deepcopy(payload);bad['inventory']['objects'][0]['ports'][0]['origin_xyz_m'][2]=float('inf')
    assert validate_extract_payload(bad)
