"""Source-bound BIM mapping, physical-connector diagnostics and immutable revisions.

No distance-based joining, nominal-to-bore substitution or code approval is inferred.
"""
from collections import Counter, defaultdict, deque
from copy import deepcopy
import json
import math
from bim.revit_handoff import checksum

SERVICES = ('UNMAPPED', 'cold_water', 'hot_water', 'hot_water_return', 'drainage', 'vent', 'storm', 'fire')


def revit_inventory(payload):
    """Adapt old extracts conservatively; new extracts carry the full port inventory."""
    from bim.schemas import validate_extract_payload
    errors = validate_extract_payload(payload)
    if errors:
        raise ValueError('; '.join(errors))
    if 'inventory' in payload:
        inventory = deepcopy(payload['inventory'])
    else:
        objects = []
        for group, kind in [('pipes','pipe'), ('fixtures','fixture'), ('tanks','tank'), ('pumps','pump'), ('valves','valve')]:
            for item in payload.get(group, []):
                objects.append(dict(source_id=item.get('revit_unique_id') or 'ELEMENT:'+item['revit_element_id'],
                    element_id=item['revit_element_id'], source_class=group, kind=kind,
                    name=item.get('family', '')+' '+item.get('type_name', ''), system=item.get('system',''),
                    nominal_mm=item.get('nominal_diameter_mm'), flow_lps=item.get('flow_lps'),
                    length_m=item.get('length_m'), start_xyz_m=item.get('start_xyz_m'), end_xyz_m=item.get('end_xyz_m'),
                    ports=[], parameters=item.get('parameters',{})))
        inventory = dict(objects=objects, connections=[], limitations=['Legacy extract has no physical port evidence; re-extract with Phase 4A.'])
    inventory.update(format='REVIT', model_id=payload.get('revit_model_id') or payload['revit_model_name'],
        source_sha256=checksum(payload), filename=payload['revit_model_name'], revision=payload.get('model_revision'),
        extract_scope=payload.get('extract_scope','UNKNOWN'), skipped=payload.get('skipped',[]))
    return inventory


def initial_mapping(inventory):
    return [dict(source_id=o['source_id'], include=True, system=o.get('system',''), service='UNMAPPED',
        nominal_mm=None, internal_mm=None, design_flow_lps=None, elevation_m=None,
        invert_start_m=None, invert_end_m=None, upstream_port='', downstream_port='',
        direction_confirmed=False, connectivity_basis='SOURCE_PORTS',
        requires_water=False, requires_drainage=False, fixture_requirements_reviewed=False,
        engineering_reviewer='', evidence_reference='', exclusion_reason='') for o in inventory['objects']]


def initial_boundaries(inventory):
    return [dict(port_id=p['source_id'], intentional_terminal=False, engineering_reviewer='', evidence_reference='')
        for o in inventory['objects'] for p in o.get('ports',[])]


def _number(row, key, positive=False):
    value = row.get(key)
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)
                              or (positive and value <= 0)):
        raise ValueError(key+' must be a finite '+('positive ' if positive else '')+'number or missing')


def diagnostics(inventory, mapping, boundaries=()):
    """Diagnose declared source topology, preserving incomplete/partitioned evidence."""
    if not isinstance(inventory,dict) or not isinstance(inventory.get('objects'),list) or len(inventory['objects']) > 10000:
        raise ValueError('Inventory requires up to 10000 explicit source objects')
    json.dumps([inventory,mapping,list(boundaries)], allow_nan=False)
    findings = []
    def issue(check, status, source, detail):
        findings.append(dict(check=check,status=status,source_id=source,detail=detail))
    ids = [o.get('source_id') for o in inventory['objects']]
    if any(not isinstance(i,str) or not i.strip() for i in ids):
        raise ValueError('Source objects require stable string identities')
    duplicates = [i for i,c in Counter(ids).items() if c>1]
    port_rows = [(p,o['source_id']) for o in inventory['objects'] for p in o.get('ports',[])]
    port_ids = [p.get('source_id') for p,_ in port_rows]
    if any(not isinstance(i,str) or not i.strip() for i in port_ids):
        raise ValueError('Ports require stable string identities')
    duplicate_ports = [i for i,c in Counter(port_ids).items() if c>1]
    for identity in duplicates+duplicate_ports:
        issue('duplicate_ids','ERROR',identity,'Identity is repeated; repair the extract before mapping or calculation.')
    if duplicates or duplicate_ports:
        return _report(inventory,mapping,findings,[],False)
    objects={o['source_id']:o for o in inventory['objects']}
    if not isinstance(mapping,list) or len(mapping)!=len(ids) or {r.get('source_id') for r in mapping}!=set(ids):
        raise ValueError('Map every source object exactly once, without foreign IDs')
    mapped={r['source_id']:r for r in mapping}
    active={}
    for r in mapping:
        if type(r.get('include')) is not bool:
            raise ValueError('Include must be Boolean')
        if not r['include']:
            if not r.get('exclusion_reason','').strip(): issue('scope','MISSING_DATA',r['source_id'],'Excluded object requires a reason.')
            continue
        active[r['source_id']]=r
        if r.get('service') not in SERVICES:
            raise ValueError('Unknown mapped service')
        for k in ('nominal_mm','internal_mm'):
            _number(r,k,True)
        for k in ('design_flow_lps','elevation_m','invert_start_m','invert_end_m'):
            _number(r,k)
        if r.get('design_flow_lps') is not None and r['design_flow_lps']<0:
            issue('reversed_flow','WARNING',r['source_id'],'Signed flow is negative relative to the reviewed orientation; confirm direction.')
        if not r.get('engineering_reviewer','').strip() or not r.get('evidence_reference','').strip():
            issue('mapping_review','MISSING_DATA',r['source_id'],'Name the engineering reviewer and source/evidence reference for this row.')
        if not r.get('system','').strip() or r['service']=='UNMAPPED':
            issue('system_service','MISSING_DATA',r['source_id'],'Explicit system and service mapping required.')
        if r.get('connectivity_basis')!='SOURCE_PORTS':
            issue('connectivity_basis','MISSING_DATA',r['source_id'],'Only extracted physical source ports are supported; revise the source or provide a new extract.')
        if r.get('elevation_m') is None:
            issue('missing_elevations','MISSING_DATA',r['source_id'],'Reviewed elevation/datum missing; centreline and invert are distinct.')
        if objects[r['source_id']]['kind']=='pipe' and (r.get('nominal_mm') is None or r.get('internal_mm') is None or r.get('design_flow_lps') is None):
            issue('pipe_inputs','MISSING_DATA',r['source_id'],'Nominal diameter, actual bore and reviewed design flow are separate inputs.')
    ports={p['source_id']:(p,owner) for p,owner in port_rows}
    boundary={}
    for b in boundaries:
        if b.get('port_id') not in ports or b['port_id'] in boundary:
            raise ValueError('Boundary port is foreign or repeated')
        if type(b.get('intentional_terminal')) is not bool:
            raise ValueError('Intentional terminal must be Boolean')
        if b['intentional_terminal'] and (not b.get('engineering_reviewer','').strip() or not b.get('evidence_reference','').strip()):
            raise ValueError('Intentional terminals require reviewer and evidence')
        boundary[b['port_id']]=b
    adjacency={i:set() for i in active}; linked=set()
    for link in inventory.get('connections',[]):
        a,b=link.get('from_port'),link.get('to_port')
        if a not in ports or b not in ports:
            issue('external_connection','MISSING_DATA',str(a)+' → '+str(b),'Port lies outside this extraction partition or is missing; completeness is unknown.')
            continue
        if a==b or ports[a][1]==ports[b][1]:
            issue('invalid_connection','ERROR',a,'Physical inter-object connection references itself.')
            continue
        linked.update((a,b)); oa,ob=ports[a][1],ports[b][1]
        if oa in active and ob in active:
            adjacency[oa].add(ob);adjacency[ob].add(oa)
            direction={'SOURCE':'OUT','SINK':'IN','SOURCEANDSINK':'BOTH'}
            da=direction.get(ports[a][0].get('flow_direction'),ports[a][0].get('flow_direction'))
            db=direction.get(ports[b][0].get('flow_direction'),ports[b][0].get('flow_direction'))
            if da in ('IN','OUT') and da==db:
                issue('reversed_flow','WARNING',oa+' / '+ob,'Connected ports both declare '+da+'; inspect source flow orientation.')
    for i,r in active.items():
        o=objects[i]
        if not o.get('ports'):
            issue('connectivity','NOT_EVALUATED',i,'No physical connector inventory; no proximity join is inferred.')
        for p in o.get('ports',[]):
            if p['source_id'] not in linked and not boundary.get(p['source_id'],{}).get('intentional_terminal',False):
                issue('open_ends','WARNING',i,'Unconnected/unresolved port '+p['source_id']+'; review intentional terminals and extract scope.')
        if r['service'] in ('drainage','storm') and o['kind']=='pipe':
            s,e=r.get('invert_start_m'),r.get('invert_end_m'); run=o.get('horizontal_run_m');length=o.get('length_m')
            if r.get('direction_confirmed') is not True or s is None or e is None:
                issue('slope','MISSING_DATA',i,'Confirm source axis upstream-to-downstream and reviewed invert elevations.')
            elif o.get('axis_segment_count')!=1 or run is None or run<=1e-9:
                issue('slope','NOT_EVALUATED',i,'Vertical/curved/multi-segment axis requires separate stack or segment review.')
            elif s<e:
                issue('impossible_slopes','ERROR',i,'Drainage rises along the confirmed direction; correct orientation, datum or invert.')
            elif length is not None and math.hypot(run,s-e)>length+1e-5:
                issue('impossible_slopes','ERROR',i,'Reviewed run/fall exceeds source segment length; inconsistent units/geometry/invert.')
        up,down=r.get('upstream_port'),r.get('downstream_port')
        if up or down:
            if up==down or up not in ports or down not in ports or ports[up][1]!=i or ports[down][1]!=i:
                raise ValueError('Reviewed upstream/downstream ports must be distinct ports owned by the source object')
            if ports[up][0].get('flow_direction') in ('OUT','SOURCE') or ports[down][0].get('flow_direction') in ('IN','SINK'):
                issue('reversed_flow','WARNING',i,'Reviewed orientation conflicts with extracted port direction.')
        if o['kind']=='fixture':
            if r.get('fixture_requirements_reviewed') is not True:
                issue('fixture_connections','MISSING_DATA',i,'Review whether this fixture needs water, drainage, or both.')
                continue
            for key,services in [('requires_water',{'cold_water','hot_water'}),('requires_drainage',{'drainage'})]:
                if type(r.get(key)) is not bool: raise ValueError('Fixture requirements must be Boolean')
                if not r[key]:continue
                visited={i}; queue=deque(adjacency[i]);found=False
                while queue:
                    node=queue.popleft()
                    if node in visited:continue
                    visited.add(node)
                    if objects[node]['kind']=='pipe' and active[node]['service'] in services:found=True;break
                    if objects[node]['kind'] in ('fitting','valve'):queue.extend(adjacency[node]-visited)
                if not found:
                    issue('fixture_without_connection','WARNING',i,'No demonstrated '+key.replace('requires_','')+' pipe path through extracted fittings/valves; partition/mapping may be incomplete.')
    components=[]
    networks=defaultdict(set)
    for i,r in active.items(): networks[(r.get('system',''),r['service'])].add(i)
    for (system,service),nodes in networks.items():
        if any(not objects[i].get('ports') for i in nodes):
            components.append(dict(system=system,service=service,components=[],status='NOT_EVALUATED',source_ids=sorted(nodes)))
            issue('component_coverage','NOT_EVALUATED',system+' / '+service,
                'Physical port inventory is missing for one or more mapped objects; disconnected components cannot be established.')
            continue
        remaining=set(nodes);parts=[]
        while remaining:
            todo=[min(remaining)];part=set()
            while todo:
                i=todo.pop()
                if i in part:continue
                part.add(i);todo.extend((adjacency[i]&nodes)-part)
            remaining-=part;parts.append(sorted(part))
        components.append(dict(system=system,service=service,components=parts,status='EVALUATED'))
        if len(parts)>1:issue('disconnected_components','WARNING',system+' / '+service,str(len(parts))+' physical components in this mapped network; separate supplies/partitions may be intentional.')
    if inventory.get('skipped'):
        issue('extract_completeness','MISSING_DATA','MODEL','Extractor skipped '+str(len(inventory['skipped']))+' objects; inspect recorded reasons.')
    for obj in inventory['objects']:
        for detail in obj.get('extraction_issues',[]):issue('extract_completeness','MISSING_DATA',obj['source_id'],detail)
    return _report(inventory,mapping,findings,components,True)


def _report(inventory,mapping,findings,components,identity_valid):
    return dict(schema_version='bim-diagnostics-1', source_sha256=inventory.get('source_sha256'),
        mapping_sha256=checksum(mapping),identity_valid=identity_valid,findings=findings,networks=components,
        technical_status='FAIL' if any(f['status']=='ERROR' for f in findings) else 'PARTIAL',
        review_status='REVIEW_REQUIRED', code_compliance='NOT_EVALUATED', coverage='PARTIAL',
        limitations=['Physical port evidence only; geometric proximity is not connectivity.',
            'Diagnostics do not solve hydraulics, infer pipe bore, approve code criteria or certify model completeness.'])


def snapshot(inventory, mapping, boundaries, reviewer, evidence):
    if not reviewer.strip() or not evidence.strip():raise ValueError('Snapshot requires reviewer and evidence')
    report=diagnostics(inventory,mapping,boundaries)
    if not report['identity_valid']:raise ValueError('Duplicate identities prevent a stable snapshot')
    body=deepcopy(dict(schema_version='bim-snapshot-1',model_id=inventory['model_id'],inventory=inventory,
        mapping=mapping,boundaries=list(boundaries),engineering_reviewer=reviewer,evidence_reference=evidence,
        diagnostics=report,review_status='REVIEW_REQUIRED'))
    return dict(payload=body,sha256=checksum(body))


def validate_snapshot(packet):
    if not isinstance(packet,dict) or packet.get('sha256')!=checksum(packet.get('payload')):
        raise ValueError('Snapshot checksum mismatch')
    b=packet['payload']
    if b.get('schema_version')!='bim-snapshot-1' or b.get('model_id')!=b.get('inventory',{}).get('model_id'):
        raise ValueError('Invalid snapshot identity/schema')
    regenerated=snapshot(b['inventory'],b['mapping'],b['boundaries'],b['engineering_reviewer'],b['evidence_reference'])
    if regenerated!=packet:raise ValueError('Snapshot diagnostic contract mismatch')
    return b


def compare_snapshots(before,after):
    a,b=validate_snapshot(before),validate_snapshot(after)
    if a['model_id']!=b['model_id']:raise ValueError('Cannot compare different model identities')
    def index(body):return {o['source_id']:o for o in body['inventory']['objects']}
    old,new=index(a),index(b);changes=[]
    for i in sorted(old.keys()|new.keys()):
        if i not in old: changes.append(dict(source_id=i,change='ADDED',fields=[]));continue
        if i not in new: changes.append(dict(source_id=i,change='REMOVED',fields=[]));continue
        fields=[k for k in sorted(old[i].keys()|new[i].keys()) if k!='parameters' and old[i].get(k)!=new[i].get(k)]
        if fields:changes.append(dict(source_id=i,change='CHANGED',fields=fields))
    om={r['source_id']:r for r in a['mapping']};nm={r['source_id']:r for r in b['mapping']}
    connections_changed=sorted(a['inventory'].get('connections',[]),key=checksum)!=sorted(b['inventory'].get('connections',[]),key=checksum)
    boundaries_changed=sorted(a['boundaries'],key=checksum)!=sorted(b['boundaries'],key=checksum)
    result_changes=[i for i in sorted(old.keys()&new.keys()) if old[i].get('parameters')!=new[i].get('parameters')]
    return dict(model_id=a['model_id'],before_sha256=before['sha256'],after_sha256=after['sha256'],objects=changes,
        mapping_changed=om!=nm,boundaries_changed=boundaries_changed,result_parameters_changed=result_changes,
        connections_changed=connections_changed,
        recalculation_required=bool(changes) or om!=nm or boundaries_changed or connections_changed,
        review_status='REVIEW_REQUIRED')


def save_snapshot(conn,project_id,packet):
    body=validate_snapshot(packet)
    conn.execute('''CREATE TABLE IF NOT EXISTS bim_extraction_snapshots (
        project_id INTEGER NOT NULL REFERENCES projects(project_id),model_id TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,packet_json TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(project_id,model_id,snapshot_sha256))''')
    conn.execute('INSERT OR IGNORE INTO bim_extraction_snapshots(project_id,model_id,snapshot_sha256,packet_json) VALUES (?,?,?,?)',
        (project_id,body['model_id'],packet['sha256'],json.dumps(packet,allow_nan=False)))
    conn.commit()
