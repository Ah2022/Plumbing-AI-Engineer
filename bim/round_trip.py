"""Real-model harness orchestration and independently re-readable result verification.

The same import/save APIs as the UI are used. No direct calculation-table edits.
"""
from copy import deepcopy
import math
from bim.revit_handoff import checksum, build_handoff, apply_handoff, TEXT_FIELDS, NUMBER_FIELDS, FLAG_FIELDS
from bim.mapping import revit_inventory, diagnostics, snapshot, validate_snapshot, save_snapshot


def _facts(inventory):
    from bim.revit_extract import source_facts
    return dict(objects=sorted([source_facts(o) for o in inventory['objects']],key=lambda o:o['source_id']),
        connections=sorted(inventory.get('connections',[]),key=checksum),skipped=inventory.get('skipped',[]))


def prepare_analysis(conn,project_id,extract,mapping,boundaries,reviewer,evidence,velocity_limit_m_s,criterion_reference):
    if isinstance(velocity_limit_m_s,bool) or not isinstance(velocity_limit_m_s,(int,float)) or not math.isfinite(velocity_limit_m_s) or velocity_limit_m_s<=0 or not criterion_reference.strip():
        raise ValueError('A finite positive water velocity criterion and reference are required')
    inventory=revit_inventory(extract)
    packet=snapshot(inventory,mapping,boundaries,reviewer,evidence)
    report=packet['payload']['diagnostics']
    if report['technical_status']=='FAIL':raise ValueError('Resolve topology/identity errors before harness analysis')
    by_uid={r['source_id']:r for r in mapping}
    candidates=[]
    for pipe in extract.get('pipes',[]):
        if not pipe.get('revit_unique_id'):raise ValueError('Re-extract pipes with stable Revit UniqueId before harness analysis')
        row=by_uid[pipe['revit_unique_id']]
        if not row['include'] or row['service'] not in ('cold_water','hot_water','hot_water_return'):continue
        if not row['engineering_reviewer'].strip() or not row['evidence_reference'].strip():
            raise ValueError('Every calculated pipe requires a named reviewer and input evidence')
        if pipe['system'] not in ('cold_water','hot_water') or row['service']!=pipe['system']:
            raise ValueError('Source/engineering service mismatch; revise extraction classification before linked analysis')
        if row.get('internal_mm') is None or row.get('design_flow_lps') is None or row['design_flow_lps']<0:
            raise ValueError('Reviewed actual bore and nonnegative design flow required for every calculated pipe')
        candidates.append((pipe,row))
    if not candidates:raise ValueError('Harness needs at least one included, explicitly mapped water pipe with a stable UniqueId')
    from bim.exchange import import_revit_extract
    from calculations.hydraulics import velocity_from_flow
    from app.db_helpers import next_calc_id,save_calculation
    import_revit_extract(conn,project_id,extract)
    save_snapshot(conn,project_id,packet)
    import hashlib
    model_key=hashlib.sha256(inventory['model_id'].encode()).hexdigest()
    for pipe,row in candidates:
        target=conn.execute('SELECT pipe_id FROM pipes WHERE project_id=? AND revit_model_key=? AND revit_element_id=?',
            (project_id,model_key,pipe['revit_element_id'])).fetchone()
        result=velocity_from_flow(row['design_flow_lps'],row['internal_mm'],next_calc_id(conn,project_id,'bim_pipe_velocity'))
        result.calc_type='bim_pipe_velocity'
        unrounded=result.intermediate['flow_m3_s']/result.intermediate['area_m2']
        result.intermediate['unrounded_velocity_m_s']=unrounded
        result.status='PASS' if unrounded<=velocity_limit_m_s else 'FAIL'
        result.required_value=velocity_limit_m_s
        result.reference=criterion_reference
        result.inputs.update(revit_source_sha256=checksum(extract),mapping_sha256=checksum(mapping),
            engineering_reviewer=row['engineering_reviewer'],evidence_reference=row['evidence_reference'],velocity_limit_m_s=velocity_limit_m_s,
            unevaluated=['Network pressure, fixture loading, recirculation, drainage and code-governance acceptance'])
        result.notes='Supplied velocity criterion only; BIM harness results require independent engineering review.'
        save_calculation(conn,project_id,result,target_type='pipe',target_id=target[0])
    handoff=build_handoff(conn,project_id,model_key)
    if not handoff['payload']['ready_for_preflight']:raise ValueError('; '.join(handoff['payload']['blockers']))
    return dict(before=extract,snapshot=packet,handoff=handoff,calculated_elements=len(candidates),
        analysis_scope='Reviewed water-pipe velocity against a supplied criterion only',review_status='REVIEW_REQUIRED')


def verify_round_trip(before,after,handoff):
    if not isinstance(handoff,dict) or handoff.get('sha256')!=checksum(handoff.get('payload')):
        raise ValueError('Handoff checksum mismatch')
    a,b=revit_inventory(before),revit_inventory(after);body=handoff['payload']
    if a['model_id']!=b['model_id'] or a['model_id']!=body.get('model_identity'):
        raise ValueError('Round-trip model identity differs')
    if body.get('source_sha256')!=checksum(before):raise ValueError('Handoff is not bound to the before extraction')
    if body.get('blockers') or not body.get('updates'):raise ValueError('Handoff is blocked or empty')
    findings=[]
    if _facts(a)!=_facts(b):findings.append(dict(check='source_identity_geometry_connectivity',status='FAIL',detail='Source objects, stable IDs, geometry, equipment inputs or physical ports changed.'))
    old={o['source_id']:o for o in a['objects']};new={o['source_id']:o for o in b['objects']};targets=set()
    for u in body['updates']:
        uid=u.get('unique_id')
        if uid in targets:raise ValueError('Duplicate round-trip update identity')
        targets.add(uid)
        if uid not in old or uid not in new or old[uid].get('element_id')!=u['element_id'] or new[uid].get('element_id')!=u['element_id']:
            findings.append(dict(check='stable_identity',status='FAIL',detail=str(uid)+': UniqueId/ElementId mismatch'));continue
        values=u['parameters']
        if set(values)!=set(TEXT_FIELDS+NUMBER_FIELDS+FLAG_FIELDS):raise ValueError('Incomplete/non-PLM round-trip fields')
        observed=new[uid].get('parameters',{})
        for key,expected in values.items():
            actual=observed.get(key)
            if key in NUMBER_FIELDS:
                equal=type(actual) in (int,float) and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-10)
            else:equal=type(actual) is type(expected) and actual==expected
            if not equal:findings.append(dict(check='result_parameter',status='FAIL',detail=uid+': '+key+' differs after re-extraction'))
    for uid in old.keys()&new.keys()-targets:
        if old[uid].get('parameters',{})!=new[uid].get('parameters',{}):
            findings.append(dict(check='unintended_parameter_write',status='FAIL',detail=uid+': non-target PLM values changed'))
    return dict(schema_version='revit-round-trip-1',status='FAIL' if findings else 'PASS',
        model_identity=a['model_id'],before_sha256=checksum(before),after_sha256=checksum(after),handoff_sha256=handoff['sha256'],
        verified_elements=len(targets),findings=findings,review_status='REVIEW_REQUIRED',code_compliance='NOT_EVALUATED',
        validation_scope='Snapshot comparison only. A real Revit run additionally requires the native harness execution record.')


def run_in_revit(doc,DB,conn,project_id,reviewed_snapshot,classify_system,velocity_limit_m_s,criterion_reference,commit=False):
    """Extract → analyze/import → native transaction → re-extract → verify.

    Default dry-run rolls back and cannot report a round-trip PASS.
    """
    from bim.revit_extract import extract_document
    reviewed=validate_snapshot(reviewed_snapshot)
    inv=reviewed['inventory']
    if inv.get('format')!='REVIT':raise ValueError('Native harness requires a reviewed Revit extraction snapshot')
    selected=None if inv.get('extract_scope')=='Entire model' else {o['element_id'] for o in inv['objects']}
    before=extract_document(doc,DB,classify_system,selected)
    fresh=revit_inventory(before)
    if fresh['model_id']!=reviewed['model_id'] or _facts(fresh)!=_facts(inv):
        raise ValueError('Model changed since mapping review; re-extract and review before running')
    prepared=prepare_analysis(conn,project_id,before,reviewed['mapping'],reviewed['boundaries'],
        reviewed['engineering_reviewer'],reviewed['evidence_reference'],velocity_limit_m_s,criterion_reference)
    write=apply_handoff(doc,DB,prepared['handoff'],commit=commit)
    after=extract_document(doc,DB,classify_system,selected)
    result=verify_round_trip(before,after,prepared['handoff']) if write['status']=='COMMITTED' else dict(status='NOT_EXECUTED',review_status='REVIEW_REQUIRED',reason='No committed native write; dry-run or preflight evidence only')
    return dict(schema_version='revit-native-harness-1',execution_environment='REVIT_API',revit_version=doc.Application.VersionNumber,
        before=before,after=after,handoff=prepared['handoff'],write=write,verification=result,
        analysis_scope=prepared['analysis_scope'],review_status='REVIEW_REQUIRED')
