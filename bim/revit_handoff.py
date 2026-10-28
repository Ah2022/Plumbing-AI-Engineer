"""File-based Revit handoff with model/element preflight and default rollback.

Only PLM result parameters are writable. No pipe sizes or model geometry are changed.
This module is importable outside Revit; the writer receives its API objects explicitly.
"""
import hashlib
import json
import math

TEXT_FIELDS = ('PLM_Calc_ID', 'PLM_Code_Status', 'PLM_Result_Unit', 'PLM_Reference',
               'PLM_Technical_Status', 'PLM_Review_Status', 'PLM_Source_SHA256')
NUMBER_FIELDS = ('PLM_Required_Value', 'PLM_Selected_Value', 'PLM_Result_Value')
FLAG_FIELDS = ('PLM_Required_Available', 'PLM_Selected_Available', 'PLM_Result_Available')


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def model_identity(doc):
    if getattr(doc, 'IsModelInCloud', False):
        path = doc.GetCloudModelPath()
        return 'cloud:{}:{}'.format(path.GetProjectGUID(), doc.CloudModelGUID)
    return '{}:{}'.format(doc.ProjectInformation.UniqueId, doc.PathName or 'unsaved')


def pipe_facts(element, DB):
    curve = element.Location.Curve
    diameter = element.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
    if diameter is None or not diameter.HasValue:
        raise ValueError('Pipe has no source nominal diameter')
    def xyz(point):
        return [DB.UnitUtils.ConvertFromInternalUnits(v, DB.UnitTypeId.Meters) for v in (point.X, point.Y, point.Z)]
    facts = dict(length_m=DB.UnitUtils.ConvertFromInternalUnits(curve.Length, DB.UnitTypeId.Meters),
        nominal_diameter_mm=DB.UnitUtils.ConvertFromInternalUnits(diameter.AsDouble(), DB.UnitTypeId.Millimeters),
        start_xyz_m=xyz(curve.GetEndPoint(0)), end_xyz_m=xyz(curve.GetEndPoint(1)))
    manager = getattr(element, 'ConnectorManager', None)
    if manager is not None:
        facts['connected_unique_ids'] = sorted({ref.Owner.UniqueId for port in manager.Connectors for ref in port.AllRefs
            if ref.Owner.UniqueId != element.UniqueId and ref.ConnectorType != DB.ConnectorType.Logical})
    return facts


def build_handoff(conn, project_id, model_key):
    from bim.exchange import export_results_for_revit
    from reports.review_workflow import overrides
    payload = export_results_for_revit(conn, project_id, model_key)
    model = conn.execute('SELECT payload_json FROM revit_model_imports WHERE project_id=? AND model_key=?', (project_id,model_key)).fetchone()
    snapshot = json.loads(model[0]) if model else {}
    sources = {item['revit_element_id']: item for group in ('pipes','tanks','pumps','fixtures','valves') for item in snapshot.get(group,[])}
    blocked = []
    pending = {p['calc_id'] for p in overrides(conn, project_id)}
    updates = []
    for eid, result in payload['results'].items():
        if not result.get('revit_unique_id'):
            blocked.append('{}: missing captured Revit UniqueId; re-extract'.format(eid))
        if pending.intersection(result['check_ids']):
            blocked.append('{}: unresolved override proposal'.format(eid))
        fields = dict(PLM_Calc_ID=result['calc_id'], PLM_Code_Status=result['status'],
            PLM_Result_Unit=result['result_unit'] or '', PLM_Reference=result['reference'] or '',
            PLM_Technical_Status=result['technical_status'], PLM_Review_Status=result['review_status'],
            PLM_Source_SHA256=payload.get('source_sha256') or '')
        for source, target, flag in [('required_value',NUMBER_FIELDS[0],FLAG_FIELDS[0]),
                                     ('selected_value',NUMBER_FIELDS[1],FLAG_FIELDS[1]),
                                     ('result_value',NUMBER_FIELDS[2],FLAG_FIELDS[2])]:
            value = result[source]
            fields[target] = 0. if value is None else value
            fields[flag] = 0 if value is None else 1
        updates.append(dict(element_id=eid, unique_id=result.get('revit_unique_id'),
            source=sources.get(eid,{}), parameters=fields))
    if not payload.get('model_identity') or not payload.get('source_sha256'):
        blocked.append('No captured model identity/source snapshot; re-extract')
    if not updates:
        blocked.append('No current linked calculations are available for this model')
    body = dict(schema_version='revit-handoff-1', project_id=project_id, model_identity=payload.get('model_identity'),
        model_key=model_key, source_sha256=payload.get('source_sha256'), updates=updates, blockers=blocked,
        ready_for_preflight=not blocked, review_status='REVIEW_REQUIRED',
        limitations=['Preview/default rollback does not certify the plumbing design.',
            'Only PLM result fields are in scope; geometry, sizes and project approval are unchanged.',
            'Re-extract after model edits. UniqueId and source geometry are checked before any write.'])
    return dict(payload=body, sha256=checksum(body))


def preflight_handoff(doc, DB, packet):
    if not isinstance(packet, dict) or not isinstance(packet.get('payload'),dict) or packet.get('sha256') != checksum(packet['payload']):
        raise ValueError('Revit handoff checksum does not match its contents')
    body = packet['payload']
    if body.get('schema_version') != 'revit-handoff-1' or body.get('model_identity') != model_identity(doc):
        raise ValueError('Handoff targets a different model or unsupported schema')
    updates = body.get('updates')
    if not isinstance(updates,list) or len(updates)>10000 or not all(isinstance(u,dict) for u in updates):
        raise ValueError('Handoff updates must be a list of up to 10000 element objects')
    errors = list(body.get('blockers') or [])
    operations = []
    seen = set()
    for update in updates:
        eid = update.get('element_id')
        if eid in seen:
            raise ValueError('Duplicate handoff element')
        seen.add(eid)
        unique_id = update.get('unique_id')
        element = doc.GetElement(unique_id) if isinstance(unique_id,str) and unique_id else None
        if element is None or str(element.Id.Value if hasattr(element.Id,'Value') else element.Id.IntegerValue) != eid:
            errors.append('{}: element identity no longer matches'.format(eid)); continue
        source = update.get('source',{})
        if not isinstance(source,dict):
            raise ValueError('Handoff source evidence must be an object')
        if source.get('source_facts') is not None:
            from bim.revit_extract import extract_element,source_facts
            try:
                facts=source['source_facts']
                current,_=extract_element(doc,DB,element,facts['kind'])
                if checksum(source_facts(current))!=checksum(facts):
                    errors.append('{}: source object/ports/equipment inputs changed; re-extract'.format(eid))
            except Exception as error:
                errors.append('{}: source facts cannot be validated: {}'.format(eid,error))
        if source.get('type_unique_id'):
            typed = doc.GetElement(element.GetTypeId())
            if typed is None or typed.UniqueId != source['type_unique_id']:
                errors.append('{}: source family/type changed; re-extract'.format(eid))
        if source.get('length_m') is not None:
            try:
                current = pipe_facts(element,DB)
                for field in ('length_m','nominal_diameter_mm'):
                    if not math.isclose(current[field],source[field],rel_tol=1e-9,abs_tol=1e-6):
                        errors.append('{}: source {} changed; re-extract'.format(eid,field))
                for field in ('start_xyz_m','end_xyz_m'):
                    if source.get(field) is not None:
                        if not isinstance(source[field],list) or len(source[field])!=3:
                            raise ValueError('Source endpoints require three SI coordinates')
                        if any(not isinstance(b,(int,float)) or isinstance(b,bool) or not math.isfinite(b) or abs(a-b)>1e-6 for a,b in zip(current[field],source[field])):
                            errors.append('{}: source position changed; re-extract'.format(eid))
                if source.get('connected_unique_ids') is not None and current.get('connected_unique_ids') != source['connected_unique_ids']:
                    errors.append('{}: source connector relationships changed; re-extract'.format(eid))
            except (AttributeError,TypeError,ValueError,KeyError) as error:
                errors.append('{}: cannot validate source geometry: {}'.format(eid,error))
        values = update.get('parameters',{})
        if set(values) != set(TEXT_FIELDS+NUMBER_FIELDS+FLAG_FIELDS):
            raise ValueError('Handoff contains an incomplete or non-PLM parameter set')
        for name, value in values.items():
            expected = DB.StorageType.String if name in TEXT_FIELDS else DB.StorageType.Integer if name in FLAG_FIELDS else DB.StorageType.Double
            parameter = element.LookupParameter(name)
            if parameter is None or parameter.IsReadOnly or parameter.StorageType != expected:
                errors.append('{}: missing, read-only or incorrectly typed {}'.format(eid,name)); continue
            if name in NUMBER_FIELDS and parameter.Definition.GetDataType() != DB.SpecTypeId.Number:
                errors.append('{}: {} must be a dimensionless Number parameter, not a native length/flow'.format(eid,name)); continue
            if name in TEXT_FIELDS and not isinstance(value,str):
                raise ValueError('PLM text fields require strings')
            if name in NUMBER_FIELDS and (isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value)):
                raise ValueError('PLM numeric fields require finite numbers')
            if name in FLAG_FIELDS and (type(value) is not int or value not in (0,1)):
                raise ValueError('PLM availability flags must be 0 or 1')
            if name == 'PLM_Source_SHA256' and value != body.get('source_sha256'):
                raise ValueError('PLM source fingerprint differs from the handoff snapshot')
            if name == 'PLM_Code_Status' and value == 'PASS' and values.get('PLM_Review_Status') != 'VERIFIED':
                raise ValueError('Unverified results cannot be written as a code PASS')
            operations.append((parameter,float(value) if name in NUMBER_FIELDS else value))
    return dict(can_write=not errors and bool(operations), errors=errors, operations=operations, element_count=len(seen))


def apply_handoff(doc, DB, packet, commit=False):
    plan = preflight_handoff(doc,DB,packet)
    if not plan['can_write']:
        return dict(status='BLOCKED', errors=plan['errors'], written=0)
    transaction = DB.Transaction(doc,'PLM reviewed result handoff')
    if transaction.Start() != DB.TransactionStatus.Started:
        transaction.Dispose()
        raise ValueError('Revit transaction did not start')
    try:
        # Repeat validation inside the transaction so the prepared values cannot race an intervening edit.
        plan = preflight_handoff(doc,DB,packet)
        if not plan['can_write']:
            raise ValueError('Handoff source/parameter state changed after preview')
        for parameter, value in plan['operations']:
            if not parameter.Set(value):
                raise ValueError('A PLM parameter rejected its value; all writes are rolled back')
        if commit:
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Revit did not commit the handoff')
            return dict(status='COMMITTED', written=plan['element_count'])
        if transaction.RollBack() != DB.TransactionStatus.RolledBack:
            raise ValueError('Revit did not confirm rollback; no successful dry run is claimed')
        return dict(status='DRY_RUN_ROLLED_BACK', written=0, tested_elements=plan['element_count'])
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise
    finally:
        transaction.Dispose()
