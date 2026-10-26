"""Deterministic tree-network design checks in explicit SI units.

This is a design-envelope evaluator, not a looped-network/transient solver.
Criteria and manufacturer catalogues are explicit inputs, never invented.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import math

from calculations.validation import finite,checked_numeric
from calculations.hydraulics import G
from models import MissingCodeDataError


def _required_text(record,key):
    value=record.get(key)
    if not isinstance(value,str) or not value.strip(): raise ValueError(f'{key} must be a nonempty string')
    return value


def validate_tree(model, *, toward_outlet=False):
    if not isinstance(model,dict) or model.get('schema_version')!='1.0' or model.get('units')!='SI':
        raise ValueError('Network requires schema_version=1.0 and explicit SI units')
    _required_text(model,'basis_reference')
    nodes,edges={},{}
    for group,target in [('nodes',nodes),('pipes',edges)]:
        items=model.get(group)
        if not isinstance(items,list) or not items: raise ValueError(group+' must be a nonempty array')
        if len(items)>500: raise ValueError('Review network exceeds supported 500-object limit')
        for item in items:
            if not isinstance(item,dict): raise ValueError(group+' entries must be objects')
            key=_required_text(item,'id')
            if key in target: raise ValueError('Duplicate '+group+' ID: '+key)
            target[key]=item
    root=model.get('root')
    if root not in nodes: raise ValueError('Unknown network root')
    children=defaultdict(list);parent={}
    for node in nodes.values():
        finite('elevation_m',node.get('elevation_m'))
        if 'dfu' in node or 'wsfu' in node: raise ValueError('Use distinct water_wsfu and drainage_dfu fields')
    for pipe in edges.values():
        a,b=pipe.get('from_node'),pipe.get('to_node')
        if a not in nodes or b not in nodes or a==b: raise ValueError('Unknown/self-connected pipe endpoints')
        finite('length_m',pipe.get('length_m'),positive=True)
        if pipe['length_m']+1e-9<abs(nodes[a]['elevation_m']-nodes[b]['elevation_m']):
            raise ValueError('Developed pipe length is shorter than its elevation change')
        if toward_outlet: a,b=b,a
        if b==root or b in parent: raise ValueError('Loops/multiple upstream paths are unsupported')
        parent[b]=(a,pipe['id']);children[a].append((b,pipe['id']))
    order=[];queue=[root]
    for key in queue:
        if key in order: raise ValueError('Cycle detected')
        order.append(key);queue.extend(child for child,_ in children[key])
    if len(order)!=len(nodes) or len(edges)!=len(nodes)-1: raise ValueError('Disconnected/cyclic network')
    if any(nodes[root].get(k,0) for k in ('water_wsfu','drainage_dfu','design_flow_lps','continuous_flow_lps')):
        raise ValueError('Do not assign fixture demand to the source/outlet root')
    return nodes,edges,root,children,parent,order


def _catalogues(model,edges):
    materials=model.get('materials',{});catalogues=model.get('catalogues',{})
    if not isinstance(materials,dict) or not isinstance(catalogues,dict): raise ValueError('Materials and catalogues must be mappings')
    result={}
    for pid,pipe in edges.items():
        material=pipe.get('material')
        if material not in materials or material not in catalogues: raise ValueError('Missing material/catalogue mapping')
        mat=materials[material]
        if not isinstance(mat,dict): raise ValueError('Material definition must be an object')
        _required_text(mat,'reference')
        if mat.get('method')=='hazen_williams': finite('c_factor',mat.get('c_factor'),positive=True)
        elif mat.get('method')=='darcy_weisbach': finite('friction_factor',mat.get('friction_factor'),positive=True)
        else: raise ValueError('Only explicit Hazen-Williams C or Darcy friction factor is supported')
        rows=catalogues[material]
        if not isinstance(rows,list) or not rows: raise ValueError('Empty catalogue')
        ids=set();parsed=[]
        for row in rows:
            if not isinstance(row,dict): raise ValueError('Catalogue rows must be objects')
            _required_text(row,'size_id');_required_text(row,'reference')
            if row['size_id'] in ids: raise ValueError('Duplicate catalogue size ID')
            ids.add(row['size_id'])
            finite('nominal_mm',row.get('nominal_mm'),positive=True)
            finite('internal_mm',row.get('internal_mm'),positive=True)
            parsed.append(row)
        result[pid]=sorted(parsed,key=lambda r:(r['internal_mm'],r['nominal_mm'],r['size_id']))
    return materials,result


@checked_numeric
def analyze_water_network(model, *, demand_lookup=None, select_sizes=False):
    nodes,edges,root,children,parent,order=validate_tree(model)
    if model.get('service') not in ('cold_water','hot_water'): raise ValueError('Declare cold_water or hot_water service with separately allocated demand')
    if nodes[root].get('kind')!='source': raise ValueError('Water root must be a source')
    available=finite('available_head_m',model.get('available_head_m'),minimum=0)
    limit=finite('velocity_limit_m_s',model.get('velocity_limit_m_s'),positive=True)
    _required_text(model,'velocity_reference')
    flow_basis=model.get('flow_basis')
    if flow_basis not in ('explicit_terminal_flows','wsfu_table'): raise ValueError('Declare a supported water flow basis')
    if flow_basis=='wsfu_table' and demand_lookup is None: raise MissingCodeDataError('WSFU demand lookup','No selected-code demand adapter')
    materials,catalogues=_catalogues(model,edges)
    wsfu={};continuous={};explicit={};terminals=[]
    for key in reversed(order):
        node=nodes[key]
        w=finite('water_wsfu',node.get('water_wsfu',0),minimum=0)
        c=finite('continuous_flow_lps',node.get('continuous_flow_lps',0),minimum=0)
        e=finite('design_flow_lps',node.get('design_flow_lps',0),minimum=0)
        if flow_basis=='explicit_terminal_flows' and w: raise ValueError('Do not mix explicit terminal flows with WSFU demand')
        if flow_basis=='wsfu_table' and e: raise ValueError('Do not mix explicit terminal flows with WSFU demand')
        if w or c or e: _required_text(node,'demand_reference')
        if (w or c or e) and node.get('kind')!='fixture': raise ValueError('Assign terminal demand to an explicit fixture node, not a junction')
        if node.get('kind')=='fixture' and children[key]: raise ValueError('Fixture terminals cannot feed downstream pipes; add a separate junction')
        if not children[key] and key!=root:
            if node.get('kind')!='fixture' or not (w+c+e)>0: raise ValueError('Terminal fixture is missing its demand/classification')
            finite('required_residual_head_m',node.get('required_residual_head_m'),minimum=0)
            terminals.append(key)
        wsfu[key]=w+sum(wsfu[n] for n,_ in children[key])
        continuous[key]=c+sum(continuous[n] for n,_ in children[key])
        explicit[key]=e+sum(explicit[n] for n,_ in children[key])
    if not terminals: raise ValueError('No terminal fixtures to check')
    flows={};demand_trace={};indices={};eligible={}
    for node in order[1:]:
        pid=parent[node][1];pipe=edges[pid]
        if flow_basis=='wsfu_table' and wsfu[node]>0:
            d=demand_lookup(wsfu[node])
            if not isinstance(d,dict) or d.get('unit')!='L/s': raise MissingCodeDataError('Typed demand result','Demand adapter must return L/s with provenance')
            finite('design_flow_lps',d.get('flow_lps'),minimum=0);_required_text(d,'reference')
            flows[pid]=d['flow_lps']+continuous[node];demand_trace[pid]=d
        else:
            flows[pid]=explicit[node]+continuous[node]
            demand_trace[pid]={'reference':model['basis_reference'],'unit':'L/s','flow_lps':flows[pid],'classification':'PROJECT'}
        finite('minimum_nominal_mm',pipe.get('minimum_nominal_mm'),positive=True)
        _required_text(pipe,'minimum_size_reference');_required_text(pipe,'losses_reference')
        finite('fittings_k',pipe.get('fittings_k'),minimum=0)
        finite('equipment_loss_m',pipe.get('equipment_loss_m'),minimum=0)
        valid=[i for i,row in enumerate(catalogues[pid]) if row['nominal_mm']>=pipe['minimum_nominal_mm'] and
               (flows[pid]/1000)/(math.pi*(row['internal_mm']/1000)**2/4)<=limit+1e-12]
        if not valid: raise MissingCodeDataError('Available pipe size','No catalogue size satisfies velocity and nominal minimum for '+pid)
        eligible[pid]=valid
        if select_sizes: indices[pid]=valid[0]
        else:
            matches=[i for i,row in enumerate(catalogues[pid]) if row['size_id']==pipe.get('selected_size_id')]
            if not matches: raise ValueError('Selected catalogue size not found for '+pid)
            indices[pid]=matches[0]

    def evaluate():
        pipe_results={};heads={root:available};paths={root:[]}
        for key in order[1:]:
            upstream,pid=parent[key];pipe=edges[pid];row=catalogues[pid][indices[pid]];mat=materials[pipe['material']]
            q=flows[pid]/1000;d=row['internal_mm']/1000;v=q/(math.pi*d*d/4)
            if mat['method']=='hazen_williams': friction=10.67*pipe['length_m']*q**1.852/(mat['c_factor']**1.852*d**4.8704)
            else: friction=mat['friction_factor']*pipe['length_m']/d*v*v/(2*G)
            fitting=pipe['fittings_k']*v*v/(2*G);equipment=pipe['equipment_loss_m']
            heads[key]=heads[upstream]-(nodes[key]['elevation_m']-nodes[upstream]['elevation_m'])-friction-fitting-equipment
            paths[key]=paths[upstream]+[pid]
            ok=v<=limit+1e-12 and row['nominal_mm']>=pipe['minimum_nominal_mm']
            pipe_results[pid]=dict(pipe_id=pid,flow_lps=flows[pid],water_wsfu=wsfu[key],
                selected_size_id=row['size_id'],nominal_mm=row['nominal_mm'],internal_mm=row['internal_mm'],
                velocity_m_s=v,friction_loss_m=friction,fitting_loss_m=fitting,equipment_loss_m=equipment,
                technical_status='PASS' if ok else 'FAIL',catalogue_reference=row['reference'],
                material_reference=mat['reference'],minimum_size_reference=pipe['minimum_size_reference'],
                demand=demand_trace[pid])
        terminal_results={key:dict(terminal_id=key,available_head_m=heads[key],
            required_head_m=nodes[key]['required_residual_head_m'],margin_m=heads[key]-nodes[key]['required_residual_head_m'],path=paths[key]) for key in terminals}
        governing=min(terminals,key=lambda k:(terminal_results[k]['margin_m'],k))
        return pipe_results,terminal_results,governing

    budget=sum(len(rows) for rows in catalogues.values())+1
    for _ in range(budget):
        pipe_results,terminal_results,governing=evaluate()
        if not select_sizes or terminal_results[governing]['margin_m']>=-1e-9: break
        old=terminal_results[governing]['margin_m'];options=[]
        for pid in terminal_results[governing]['path']:
            next_indices=[i for i in eligible[pid] if i>indices[pid]]
            if not next_indices: continue
            original=indices[pid];indices[pid]=next_indices[0]
            _,trial,_=evaluate()
            options.append((trial[governing]['margin_m']-old,pid,next_indices[0]))
            indices[pid]=original
        if not options or max(options)[0]<=1e-12: break
        choice=max(options);indices[choice[1]]=choice[2]
    pipe_results,terminal_results,governing=evaluate()
    ok=all(r['technical_status']=='PASS' for r in pipe_results.values()) and all(r['margin_m']>=-1e-9 for r in terminal_results.values())
    return dict(schema_version='1.0',system='water',service=model['service'],technical_status='PASS' if ok else 'FAIL',
        review_status='REVIEW_REQUIRED',governing_terminal=governing,governing_path=terminal_results[governing]['path'],
        minimum_pressure_margin_m=terminal_results[governing]['margin_m'],pipes=list(pipe_results.values()),
        terminals=list(terminal_results.values()),input_sha256=hashlib.sha256(json.dumps(model,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        limitations=['Tree design envelope only; loops, multiple pressure zones, transients and simultaneous diversity scenarios are not solved.',
                     'Greedy catalogue upsizing finds a feasible supported design, not a globally least-cost design.',
                     'Code applicability, source pressure conditions, equipment loss curves and independent engineering approval remain required.'])


@checked_numeric
def analyze_drainage_network(conn,code_id,model):
    from calculations.drainage import size_drainage_pipe,check_min_slope
    nodes,edges,root,children,parent,order=validate_tree(model,toward_outlet=True)
    if nodes[root].get('kind')!='outlet': raise ValueError('Drainage root must be the outlet')
    loads={};intervals={};unassigned={};checks=[]
    for key in reversed(order):
        node=nodes[key];local=finite('drainage_dfu',node.get('drainage_dfu',0),minimum=0)
        if local: _required_text(node,'demand_reference')
        if not children[key] and key!=root and (node.get('kind')!='fixture' or local<=0):
            raise ValueError('Terminal drainage fixture is missing its DFU classification')
        loads[key]=local+sum(loads[n] for n,_ in children[key])
        intervals[key]=defaultdict(float)
        unassigned[key]=sum(unassigned[n] for n,_ in children[key])
        if local:
            interval=node.get('branch_interval')
            if interval is None: unassigned[key]+=local
            elif isinstance(interval,bool) or not isinstance(interval,int) or interval<1:
                raise ValueError('branch_interval must be a positive integer')
            else: intervals[key][interval]+=local
        for child,_ in children[key]:
            for interval,load in intervals[child].items(): intervals[key][interval]+=load
    for key in order[1:]:
        down,pid=parent[key];pipe=edges[pid]
        nominal=finite('nominal_mm',pipe.get('nominal_mm'),positive=True)
        horizontal=finite('horizontal_run_m',pipe.get('horizontal_run_m'),minimum=0)
        drop=nodes[key]['elevation_m']-nodes[down]['elevation_m']
        if pipe['length_m']+1e-9<math.hypot(horizontal,drop): raise ValueError('Pipe length contradicts drainage geometry')
        geometry_ok=drop>0 if horizontal==0 else drop>=0
        slope=drop/horizontal*100 if horizontal>0 else None
        kind=pipe.get('context')
        if kind not in ('horizontal_branch','stack_le3_branch_intervals','stack_gt3_branch_intervals','branch_interval','building_drain','building_sewer'):
            raise ValueError('Declare the drainage segment context')
        if horizontal==0 and kind in ('horizontal_branch','building_drain','building_sewer'):
            raise ValueError('Horizontal context requires a horizontal run')
        try:
            finite('minimum_nominal_mm',pipe.get('minimum_nominal_mm'),positive=True)
            _required_text(pipe,'minimum_size_reference')
            if pipe.get('has_offset'):
                checks.append(dict(pipe_id=pid,technical_status='NOT_EVALUATED',reason='Stack/branch offsets require a separate supported arrangement rule'))
                continue
            required=size_drainage_pipe(conn,code_id,loads[key],kind,'NET-'+pid,selected_slope_pct=slope)
            required_size=max(required.result_value,pipe['minimum_nominal_mm'])
            capacity_checks=[required]
            source_size_ok=True
            if required.intermediate.get('source_nominal_unit')=='in':
                selected_in=pipe.get('selected_source_nominal_in')
                if selected_in is None: raise MissingCodeDataError('Nominal-size designation mapping','Supply selected_source_nominal_in; DN is not inches converted to millimetres')
                finite('selected_source_nominal_in',selected_in,positive=True)
                source_size_ok=selected_in>=required.intermediate['source_nominal_value']
            if kind in ('stack_le3_branch_intervals','stack_gt3_branch_intervals'):
                count=pipe.get('branch_intervals')
                if isinstance(count,bool) or not isinstance(count,int) or count<1:
                    raise ValueError('Stack branch_intervals count is required')
                if (kind=='stack_le3_branch_intervals' and count>3) or (kind=='stack_gt3_branch_intervals' and count<=3):
                    raise ValueError('Stack context contradicts branch interval count')
                if unassigned[key] or any(i>count for i in intervals[key]):
                    raise MissingCodeDataError('Stack branch-interval classification','Assign every contributing fixture to an interval within the declared stack')
                if kind=='stack_gt3_branch_intervals':
                    for interval,load in intervals[key].items():
                        per_interval=size_drainage_pipe(conn,code_id,load,'branch_interval','NET-I-'+pid)
                        required_size=max(required_size,per_interval.result_value)
                        capacity_checks.append(per_interval)
                        if per_interval.intermediate.get('source_nominal_unit')=='in':
                            selected_in=pipe.get('selected_source_nominal_in')
                            if selected_in is None: raise MissingCodeDataError('Nominal-size designation mapping','Supply selected_source_nominal_in for branch-interval sizing')
                            finite('selected_source_nominal_in',selected_in,positive=True)
                            source_size_ok=source_size_ok and selected_in>=per_interval.intermediate['source_nominal_value']
            size_ok=(nominal+1e-9>=pipe['minimum_nominal_mm'] and source_size_ok) if required.intermediate.get('source_nominal_unit')=='in' else nominal+1e-9>=required_size
            min_slope=None;slope_ok=True;reference='; '.join(dict.fromkeys(c.reference for c in capacity_checks))
            flagged=any(c.status!='PASS' for c in capacity_checks)
            if horizontal>0:
                if 'minimum_slope_pct' in pipe:
                    min_slope=finite('minimum_slope_pct',pipe['minimum_slope_pct'],positive=True)
                    _required_text(pipe,'minimum_slope_reference')
                    reference+='; supplied criterion: '+pipe['minimum_slope_reference']
                else:
                    s=check_min_slope(conn,code_id,nominal,slope,'NET-S-'+pid)
                    min_slope=s.required_value;reference+='; '+s.reference
                    flagged=flagged or s.status=='WARNING'
                slope_ok=slope+1e-9>=min_slope
            status=('WARNING' if flagged else 'PASS') if geometry_ok and size_ok and slope_ok else 'FAIL'
            checks.append(dict(pipe_id=pid,drainage_dfu=loads[key],context=kind,required_nominal_mm=required_size,
                selected_nominal_mm=nominal,actual_slope_pct=slope,minimum_slope_pct=min_slope,technical_status=status,
                reference=reference,confidence='FLAGGED' if flagged else 'CONFIRMED'))
        except MissingCodeDataError as e:
            checks.append(dict(pipe_id=pid,drainage_dfu=loads[key],technical_status='MISSING_DATA',reason=str(e)))
    vents=[]
    from calculations.vent import check_vent_arrangement
    if not isinstance(model.get('vents',[]),list): raise ValueError('vents must be an array')
    for vent in model.get('vents',[]):
        if not isinstance(vent,dict): raise ValueError('Vent entries must be objects')
        fixture_node=vent.get('load_node')
        if fixture_node not in loads: raise ValueError('Unknown vent load node')
        vents.append(check_vent_arrangement(conn,code_id,vent,loads[fixture_node]))
    statuses=[c['technical_status'] for c in checks+vents]
    status='FAIL' if 'FAIL' in statuses else 'WARNING' if any(s!='PASS' for s in statuses) or not vents else 'PASS'
    return dict(schema_version='1.0',system='drainage',technical_status=status,review_status='REVIEW_REQUIRED',
        total_drainage_dfu=loads[root],pipes=checks,vents=vents,coverage_status='PARTIAL',
        input_sha256=hashlib.sha256(json.dumps(model,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        limitations=['DFU sizing and explicit slope/vent checks only; full code compliance is not established.',
                     'Cleanouts, branch intervals, trap protection, special venting, fire stopping and backwater/secondary arrangements require separate review.',
                     'No gravity discharge flow is inferred from DFU; partial-flow hydraulics are not solved.'])
