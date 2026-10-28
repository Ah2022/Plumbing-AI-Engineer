"""Read-only Revit API adapter. Native units become SI; missing facts stay missing.

Called in Revit CPython3; API types are injected for offline contract tests.
"""
import datetime
import math
from bim.revit_handoff import model_identity, pipe_facts, TEXT_FIELDS, NUMBER_FIELDS, FLAG_FIELDS


def element_id(element):
    return str(element.Id.Value if hasattr(element.Id,'Value') else element.Id.IntegerValue)


def _text(element,name):
    p=element.LookupParameter(name)
    return p.AsString() if p and p.HasValue and str(p.StorageType)=='String' else None


def _name(element,DB):
    if element is None:return None
    try:return DB.Element.Name.__get__(element)
    except (AttributeError,TypeError):return element.Name


def _parameter(element, DB, token, unit):
    bip=getattr(DB.BuiltInParameter,token,None)
    p=element.get_Parameter(bip) if bip is not None else None
    if p is None or not p.HasValue:return None
    value=DB.UnitUtils.ConvertFromInternalUnits(p.AsDouble(),unit)
    if not math.isfinite(value):raise ValueError('Nonfinite '+token)
    return value


def _xyz(point,DB):
    return [DB.UnitUtils.ConvertFromInternalUnits(v,DB.UnitTypeId.Meters) for v in (point.X,point.Y,point.Z)]


def _manager(element):
    manager=getattr(element,'ConnectorManager',None)
    return manager if manager is not None else getattr(getattr(element,'MEPModel',None),'ConnectorManager',None)


def physical_ports(element,DB):
    manager=_manager(element)
    if manager is None:return [],[],['No ConnectorManager exposed']
    ports=[];links=[];issues=[]
    def physical(port):
        return str(port.Domain)=='DomainPiping' and str(port.ConnectorType) in ('End','Curve','Physical')
    def key(port):return port.Owner.UniqueId+':'+str(port.Id)
    for port in manager.Connectors:
        try:
            if not physical(port):continue
            row=dict(source_id=key(port),origin_xyz_m=_xyz(port.Origin,DB),flow_direction='UNKNOWN')
            try:
                row['flow_direction']={'In':'IN','Out':'OUT','Bidirectional':'BOTH'}.get(str(port.Direction),'UNKNOWN')
            except Exception as error:
                issues.append('Flow direction unavailable: '+str(error))
            ports.append(row)
            for other in port.AllRefs:
                if other.Owner.UniqueId!=element.UniqueId and physical(other) and port.IsConnectedTo(other):
                    a,b=sorted((key(port),key(other)))
                    links.append(dict(from_port=a,to_port=b,evidence='Revit physical piping connector / IsConnectedTo'))
        except Exception as error:
            issues.append('Connector extraction incomplete: '+str(error))
    return sorted(ports,key=lambda p:p['source_id']),links,issues


def extract_element(doc,DB,element,kind):
    typed=doc.GetElement(element.GetTypeId())
    ports,links,issues=physical_ports(element,DB)
    system=getattr(element,'MEPSystem',None)
    row=dict(source_id=element.UniqueId,element_id=element_id(element),kind=kind,
        source_class=element.GetType().Name,name=_name(element,DB) or '',type_unique_id=typed.UniqueId if typed else None,
        family=getattr(getattr(typed,'Family',None),'Name',None),type_name=_name(typed,DB),
        system=system.Name if system else '',ports=ports,extraction_issues=issues,
        nominal_mm=None,internal_mm=None,flow_lps=None,elevation_m=None,
        start_xyz_m=None,end_xyz_m=None,length_m=None,horizontal_run_m=None,axis_segment_count=None,
        properties=dict(equipment_class=_text(element,'PLM_Equipment_Class'),tank_type=_text(element,'PLM_Tank_Type')))
    if kind=='pipe':
        facts=pipe_facts(element,DB)
        row.update({k:v for k,v in facts.items() if k!='nominal_diameter_mm'})
        row['nominal_mm']=facts['nominal_diameter_mm']
        row['axis_segment_count']=1 if isinstance(element.Location.Curve,DB.Line) else None
        row['horizontal_run_m']=math.hypot(row['start_xyz_m'][0]-row['end_xyz_m'][0],row['start_xyz_m'][1]-row['end_xyz_m'][1]) if row['axis_segment_count']==1 else None
        row['internal_mm']=_parameter(element,DB,'RBS_PIPE_INNER_DIAM_PARAM',DB.UnitTypeId.Millimeters)
        row['flow_lps']=_parameter(element,DB,'RBS_PIPE_FLOW_PARAM',DB.UnitTypeId.LitersPerSecond)
        row['elevation_m']=row['start_xyz_m'][2]
    else:
        point=getattr(getattr(element,'Location',None),'Point',None)
        if point is not None:row['elevation_m']=_xyz(point,DB)[2]
    if not row['system']:
        # A family can have several services; retain each connected source system, not a guessed single service.
        manager=_manager(element)
        row['system']='; '.join(sorted({p.MEPSystem.Name for p in manager.Connectors if p.MEPSystem is not None})) if manager else ''
    parameters={}
    for name in TEXT_FIELDS+NUMBER_FIELDS+FLAG_FIELDS:
        p=element.LookupParameter(name)
        if p is None or not p.HasValue:continue
        storage=str(p.StorageType)
        if name in TEXT_FIELDS and storage=='String':parameters[name]=p.AsString() or ''
        elif name in FLAG_FIELDS and storage=='Integer':parameters[name]=p.AsInteger()
        elif name in NUMBER_FIELDS and storage=='Double' and p.Definition.GetDataType()==DB.SpecTypeId.Number:
            parameters[name]=p.AsDouble()
    row['parameters']=parameters
    return row,links


def source_facts(row):
    """PLM outputs are excluded from source geometry, connectivity and equipment inputs."""
    return {k:v for k,v in row.items() if k not in ('parameters',)}


def extract_document(doc,DB,classify_system,selected_ids=None):
    if doc.IsFamilyDocument:raise ValueError('Open a project model, not a family document')
    payload=dict(schema_version='1.0',units='SI',extractor_version='phase4a-1',revit_version=doc.Application.VersionNumber,
        revit_model_id=model_identity(doc),revit_model_name=doc.Title,
        extracted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        extract_scope='Entire model' if selected_ids is None else 'Current selection',pipes=[],fixtures=[],tanks=[],pumps=[],valves=[],skipped=[])
    try:
        version=DB.Document.GetDocumentVersion(doc)
        payload['model_revision']=dict(version_guid=str(version.VersionGUID),number_of_saves=version.NumberOfSaves,is_modified=doc.IsModified)
    except Exception as error:
        payload['model_revision']=dict(unavailable=str(error))
    objects=[];connections=[]
    categories=[('OST_PipeCurves','pipe'),('OST_PipeFitting','fitting'),('OST_PlumbingFixtures','fixture'),
        ('OST_PipeAccessory','accessory'),('OST_MechanicalEquipment','equipment'),('OST_GenericModel','equipment')]
    for category,default_kind in categories:
        for element in DB.FilteredElementCollector(doc).OfCategory(getattr(DB.BuiltInCategory,category)).WhereElementIsNotElementType():
            if selected_ids is not None and element_id(element) not in selected_ids:continue
            kind=default_kind
            if kind in ('equipment','accessory'):
                marker=(_text(element,'PLM_Equipment_Class') or '').strip().lower()
                if marker not in ('tank','pump','valve'):
                    if kind=='equipment':
                        manager=_manager(element)
                        if manager and any(str(p.Domain)=='DomainPiping' for p in manager.Connectors):
                            payload['skipped'].append(dict(element_id=element_id(element),reason='Piping equipment needs explicit PLM_Equipment_Class: tank, pump or valve'))
                        continue
                    kind='fitting' # Unclassified accessory remains topology evidence, never assumed a valve.
                else:kind=marker
            try:
                row,links=extract_element(doc,DB,element,kind)
                objects.append(row);connections.extend(links)
                if len(objects)>10000:raise OverflowError('Partition models larger than 10000 extracted objects; no truncation')
                item=dict(revit_element_id=row['element_id'],revit_unique_id=row['source_id'],type_unique_id=row['type_unique_id'],
                    source_facts=source_facts(row),parameters=row['parameters'])
                if kind=='pipe':
                    p=element.get_Parameter(DB.BuiltInParameter.RBS_SYSTEM_CLASSIFICATION_PARAM)
                    label=(p.AsString() or p.AsValueString()) if p and p.HasValue else None
                    service=classify_system(label)
                    if not service:
                        payload['skipped'].append(dict(element_id=row['element_id'],reason='Legacy linked calculation needs explicit service; object retained in mapping inventory',source_classification=label))
                        continue
                    item.update(pipe_facts(element,DB),system=service)
                    payload['pipes'].append(item)
                elif kind=='fixture':
                    item.update(family=row['family'] or '(unavailable)',type_name=row['type_name'] or '(unavailable)')
                    payload['fixtures'].append(item)
                elif kind in ('tank','pump','valve'):
                    if kind=='tank':item['tank_type']=row['properties']['tank_type'] or 'UNMAPPED'
                    payload[kind+'s'].append(item)
            except OverflowError:raise
            except Exception as error:
                payload['skipped'].append(dict(element_id=element_id(element),reason='Extraction failed: '+str(error)))
    payload['inventory']=dict(objects=sorted(objects,key=lambda o:o['source_id']),
        connections=sorted({(l['from_port'],l['to_port']):l for l in connections}.values(),key=lambda l:(l['from_port'],l['to_port'])),
        limitations=['Only physical piping connector references are captured; missing/linked/partitioned objects remain unresolved.',
            'Source bore/flow/elevation values require engineering mapping and datum review.',
            'Pump/tank/valve classification requires PLM_Equipment_Class; family names never classify equipment.'])
    from bim.schemas import validate_extract_payload
    errors=validate_extract_payload(payload)
    if errors:raise ValueError('; '.join(errors))
    return payload
