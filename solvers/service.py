"""Route the unchanged tree evaluator or an isolated EPANET 2.2 worker."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from solvers.graph import normalize_graph,topology,apply_scenario

ROOT=Path(__file__).resolve().parents[1]
LIMITATIONS=[
    'Raw EPANET2.2 flow and geometric volume use slightly different published unit-conversion constants; tree/head and storage-balance comparisons reconcile these explicitly.',
    'Hydraulic simulation is not code compliance; project adoption, applicable code rules, source criteria and independent engineering acceptance remain separate.',
    'Specified SI nodal demands must come from a reviewed plumbing demand model. Demand multipliers and fire load cases do not establish fixture diversity or fire-code compliance.',
    'Water-quality, transients, thermal/hot-water recirculation and gravity drainage are outside this pressure-network backend.',
    'Pump H-Q curves are modeled; manufacturer efficiency, NPSH, motor selection and energy approval are not established.',
    'PDA service pressures and exponent are explicit project criteria; equivalent DDA tree comparisons retain their original demand assumptions.']


def configured_library():
    raw=os.environ.get('PLUMBING_EPANET_LIBRARY') or os.environ.get('EPANET_LIBRARY')
    return Path(raw).expanduser().resolve() if raw else None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def legacy_to_graph(model):
    """Explicit flows/H-W only; never translate constant Darcy f into roughness."""
    if model.get('schema_version')!='1.0' or model.get('units')!='SI' or model.get('service') not in ('cold_water','hot_water'):raise ValueError('Only SI water models can be converted to the pressure backend')
    if model.get('flow_basis')!='explicit_terminal_flows':raise ValueError('Resolve fixture-unit diversity into referenced nodal L/s demands before general-network analysis')
    nodes=[];root=model['root'];byid={n['id']:n for n in model['nodes']}
    for node in model['nodes']:
        if node.get('water_wsfu') or node.get('drainage_dfu'):raise ValueError('Fixture units are not hydraulic flow; resolve a reviewed nodal demand model first')
        n=dict(id=node['id'],kind='source' if node['id']==root else 'junction',elevation_m=node['elevation_m'],reference=model['basis_reference'])
        if node['id']==root:n['head_m']=model['available_head_m']+node['elevation_m']
        else:n.update(demand_lps=node.get('design_flow_lps',0)+node.get('continuous_flow_lps',0),
            required_pressure_m=node.get('required_residual_head_m',0),demand_reference=node.get('demand_reference',model['basis_reference']))
        nodes.append(n)
    links=[]
    for pipe in model['pipes']:
        mat=model['materials'][pipe['material']]
        if mat.get('method')!='hazen_williams':raise ValueError('Legacy fixed Darcy friction factor has no equivalent EPANET roughness. Supply an explicit general D-W model instead')
        if pipe.get('equipment_loss_m')!=0:raise ValueError('Fixed equipment head loss cannot be discarded: map it explicitly to a supported valve or reviewed curve')
        sizes=[r for r in model['catalogues'][pipe['material']] if r['size_id']==pipe['selected_size_id']]
        if len(sizes)!=1:raise ValueError('Selected pipe size is ambiguous or absent')
        links.append(dict(id=pipe['id'],kind='pipe',from_node=pipe['from_node'],to_node=pipe['to_node'],length_m=pipe['length_m'],
            internal_mm=sizes[0]['internal_mm'],roughness=mat['c_factor'],roughness_unit='C',minor_loss_k=pipe['fittings_k'],status=pipe.get('status','OPEN'),reference=pipe['losses_reference']))
    general=dict(schema_version='pressure-network-1',units='SI',code_id=model.get('code_id'),basis_reference=model['basis_reference'],nodes=nodes,links=links)
    return normalize_graph(general)[0]


def routing(model,backend='auto'):
    if backend not in ('auto','tree','epanet'):raise ValueError('Backend must be auto, tree or epanet')
    if model.get('schema_version')=='1.0':
        nodes={r['id']:r for r in model['nodes']};topo=topology(nodes,model['pipes'])
        reasons=['looped topology'] if topo['has_loops'] else []
        # Unsupported solver features must not be silently passed to the legacy evaluator.
        if any(k in model for k in ('simulation','demand_model','controls','curves','links','scenarios','patterns')):raise ValueError('Advanced features require schema pressure-network-1; legacy tree fields cannot silently override solver options')
        if any(n.get('kind') not in ('source','junction','fixture') or any(k in n for k in ('initial_level_m','head_m','min_level_m','max_level_m','diameter_m')) for n in nodes.values()):raise ValueError('Source/tank/equipment definitions require pressure-network-1; legacy storage fields cannot be ignored')
        if any(p.get('kind','pipe')!='pipe' or any(k in p for k in ('curve_id','speed','valve_type','setting','roughness')) for p in model['pipes']):raise ValueError('Pump/valve/roughness fields require pressure-network-1')
        if any(p.get('status','OPEN')!='OPEN' for p in model['pipes']):reasons.append('closed or controlled link status')
        chosen='epanet' if backend=='epanet' or reasons else 'tree'
        if backend=='tree' and reasons:raise ValueError('Network topology/status requires EPANET; tree backend was explicitly requested')
        return dict(backend=chosen,reasons=reasons or ['legacy deterministic tree'],topology=topo)
    normalized,topo=normalize_graph(model)
    if backend=='tree':raise ValueError('General graph features require EPANET. Use the legacy tree schema for deterministic tree checks')
    reasons=['general pressure-network schema']
    if topo['has_loops']:reasons.append('looped topology')
    if normalized['simulation']['duration_s']:reasons.append('extended-period simulation')
    if normalized['demand_model']['type']=='PDA':reasons.append('pressure-dependent demand')
    if any(n['kind']=='tank' for n in normalized['nodes']):reasons.append('tank storage')
    if any(e['kind'] in ('pump','valve') for e in normalized['links']):reasons.append('pump/valve equipment')
    return dict(backend='epanet',reasons=reasons,topology=topo)


def solve_network(model,*,backend='auto',library=None,timeout_s=45,demand_lookup=None,select_sizes=False):
    route=routing(model,backend)
    if route['backend']=='tree':
        from calculations.network import analyze_water_network
        return dict(backend='tree',routing=route,result=analyze_water_network(model,demand_lookup=demand_lookup,select_sizes=select_sizes))
    if select_sizes:raise ValueError('EPANET analyzes specified bores and pump curves; automatic catalogue sizing remains a tree-layer feature')
    normalized=legacy_to_graph(model) if model.get('schema_version')=='1.0' else normalize_graph(model)[0]
    lib=Path(library).resolve() if library else configured_library()
    base=dict(backend='epanet',routing=route,schema_version='pressure-network-result-1',
        review_status='REVIEW_REQUIRED',code_compliance_status='NOT_EVALUATED',technical_status='NOT_EVALUATED',
        input_sha256=fingerprint(normalized),normalized_model=normalized,limitations=LIMITATIONS,
        governance_requirements=['Approved project design basis','Verified applicable code requirements and numeric sources',
            'Complete model-to-rule coverage','Independent engineering acceptance; solver convergence cannot provide these approvals'])
    if lib is None or not lib.is_file():
        return dict(base,solver_status='BACKEND_UNAVAILABLE',complete=False,snapshots=[],diagnostics=[dict(code='EPANET_NOT_CONFIGURED',severity='ERROR',
            message='EPANET 2.2 library is not configured or does not exist.',action='Install the official toolkit and configure PLUMBING_EPANET_LIBRARY on the server; general cases cannot fall back to the tree solver.')])
    if isinstance(timeout_s,bool) or not isinstance(timeout_s,(int,float)) or not 0<timeout_s<=60:raise ValueError('Worker timeout must be 0–60 seconds')
    with tempfile.TemporaryDirectory(prefix='plm_solver_job_') as folder:
        root=Path(folder);source=root/'model.json';target=root/'results.json';source.write_text(json.dumps(normalized,allow_nan=False),encoding='utf-8')
        try:
            process=subprocess.run([sys.executable,'-m','solvers.worker',str(source),str(target),str(lib)],cwd=ROOT,
                capture_output=True,text=True,timeout=timeout_s,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except subprocess.TimeoutExpired:
            return dict(base,solver_status='TIMEOUT',complete=False,snapshots=[],diagnostics=[dict(code='WORKER_TIMEOUT',severity='ERROR',
                message=f'Solver worker exceeded {timeout_s} seconds and was terminated.',action='Shorten the period, simplify controls and inspect connectivity/pump/valve settings before rerunning.')])
        if process.returncode or not target.is_file() or target.stat().st_size>50000000:
            return dict(base,solver_status='NOT_CONVERGED',complete=False,snapshots=[],diagnostics=[dict(code='WORKER_FAILURE',severity='ERROR',
                message='The isolated solver exited without a bounded result.',action='Check toolkit/platform compatibility, model size and local solver logs.')])
        result=json.loads(target.read_text(encoding='utf-8'));output=dict(base,**result)
    if not output['complete']:return output
    junctions=[n for s in output['snapshots'] for n in s['nodes'] if n['kind']=='junction']
    margins=[n['pressure_margin_m'] for n in junctions];deficits=[n['demand_deficit_lps'] for n in junctions]
    output.update(minimum_pressure_margin_m=min(margins),maximum_demand_deficit_lps=max(deficits),
        technical_status='FAIL' if min(margins)<-1e-6 or max(deficits)>1e-5 else 'WARNING' if output['diagnostics'] else 'PASS')
    if output['technical_status']=='FAIL':output['diagnostics'].append(dict(code='INADEQUATE_SERVICE',severity='WARNING',
        message='One or more junctions have inadequate pressure or unmet prescribed demand.',action='Inspect the time-stamped pressure margins and deficits; revise source pressure, zoning, pump duty or pipe resistance against reviewed design criteria.'))
    return output


def run_scenarios(model,scenarios=None,*,library=None):
    normalized,_=normalize_graph(model);cases=normalized['scenarios'] if scenarios is None else scenarios
    if not isinstance(cases,list) or len(cases)>10:raise ValueError('At most ten scenarios may be run')
    results=[]
    for scenario in cases:
        changed,disabled=apply_scenario(normalized,scenario)
        result=solve_network(changed,library=library)
        results.append(dict(scenario=deepcopy(scenario),disabled_controls=disabled,result=result))
    return dict(schema_version='pressure-scenarios-result-1',base_input_sha256=fingerprint(normalized),scenarios=results,
        review_status='REVIEW_REQUIRED',code_compliance_status='NOT_EVALUATED',limitations=LIMITATIONS)


def compare_tree(model,*,library=None):
    from calculations.network import analyze_water_network
    tree=analyze_water_network(model);external=solve_network(model,backend='epanet',library=library)
    rows=[]
    if external.get('complete'):
        snapshot=external['snapshots'][0];nodes={r['node_id']:r for r in snapshot['nodes']}
        flows={r['pipe_id']:r['flow_lps'] for r in tree['pipes']};losses={}
        for p in model['pipes']:
            size=next(r for r in model['catalogues'][p['material']] if r['size_id']==p['selected_size_id'])
            q=flows[p['id']]/28.317;d=size['internal_mm']/304.8;length=p['length_m']/.3048;c=model['materials'][p['material']]['c_factor']
            losses[p['id']]=.3048*(4.727*length*q**1.852/(c**1.852*d**4.871)+.02517*p['fittings_k']*q*q/d**4)
        elevations={n['id']:n['elevation_m'] for n in model['nodes']}
        for terminal in tree['terminals']:
            tid=terminal['terminal_id'];actual=nodes[tid]['pressure_m']
            expected=model['available_head_m']-(elevations[tid]-elevations[model['root']])-sum(losses[p] for p in terminal['path'])
            rows.append(dict(terminal_id=tid,tree_pressure_m=terminal['available_head_m'],epanet_pressure_m=actual,
                difference_m=actual-terminal['available_head_m'],convention_residual_m=actual-expected,
                comparison_status='MATCH_WITH_DOCUMENTED_CONVENTIONS' if abs(actual-expected)<=1e-6 else 'UNEXPLAINED_DISCREPANCY'))
    return dict(tree=tree,epanet=external,comparison=rows,review_status='REVIEW_REQUIRED',
        explanation='The unchanged SI tree and EPANET2.2 use different published H-W diameter exponents and conversion/minor-loss constants; raw differences and reconciled residuals are reported separately.')
