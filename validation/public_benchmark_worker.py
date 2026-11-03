"""Internal isolated runner. Never imports or executes upstream repository scripts."""
import csv,hashlib,io,json,math,os,sys
from pathlib import Path
from validation.public_benchmarks import screen_inp,epanet_model


def compare(name,actual,expected,tolerance=0):
    good=(math.isclose(actual,expected,rel_tol=0,abs_tol=tolerance) if isinstance(expected,(int,float)) else actual==expected)
    return dict(check=name,status='PASS' if good else 'FAIL',actual=actual,expected=expected,absolute_tolerance=tolerance)


def epanet(folder,c,library):
    from solvers.service import configured_library,solve_network
    from validation.epanet_runner import run_epanet
    library=Path(library) if library else configured_library()
    if library is None or not library.is_file():return dict(software_status='BACKEND_UNAVAILABLE',issues=['Configure PLUMBING_EPANET_LIBRARY for the optional native comparison'],comparisons=[])
    raw=(folder/'model.dat').read_bytes();screen_inp(raw,'epanet');model=epanet_model(raw)
    original=run_epanet(raw.decode('ascii'),library);mapped=solve_network(model,library=library)
    if not mapped['complete']:return dict(software_status='FAIL',issues=mapped.get('diagnostics',[]),comparisons=[])
    snapshot=mapped['snapshots'][0];checks=[]
    for node in snapshot['nodes']:
        if node['kind']!='junction':continue
        identity=node['node_id'][1:];reference=original['nodes'][identity]
        checks.extend([compare(identity+':mapped_pressure_m',node['pressure_m'],reference['pressure_m'],c['numeric_tolerance']),
            compare(identity+':mapped_demand_lps',node['delivered_demand_lps'],reference['demand_lps'],c['numeric_tolerance'])])
    for edge in snapshot['links']:
        identity=edge['link_id'][1:];checks.append(compare(identity+':mapped_flow_lps',edge['flow_lps'],original['pipes'][identity]['flow_lps'],c['numeric_tolerance']))
    checks+= [compare('upstream_node_count',len(model['nodes']),c['expected']['node_count']),compare('upstream_link_count',len(model['links']),c['expected']['link_count'])]
    warnings=original['warnings']+mapped['diagnostics']
    if any(w.get('code') in (1,2) for w in warnings):checks.append(compare('native_convergence_warning',True,False))
    return dict(software_status='PASS' if all(r['status']=='PASS' for r in checks) else 'FAIL',comparisons=checks,issues=[],
        native_version=original['version'],native_library_sha256=original['library_sha256'],warnings=warnings,
        coverage='Original native input versus explicitly mapped steady-state H-W/LPS engine graph; same-backend mapping regression, not an independent physical reference')


def swmm(folder,c):
    from swmm.toolkit import solver,output,shared_enum as E
    raw=(folder/'model.dat').read_bytes();sections=screen_inp(raw,'swmm');inp=folder/'model.inp'
    execution=raw+b'\n[REPORT]\nNODES ALL\nLINKS ALL\nSUBCATCHMENTS ALL\n'
    inp.write_bytes(execution)
    unit=next((r[1].upper() for r in sections['OPTIONS'] if r[0].upper()=='FLOW_UNITS'),'CFS')
    length=.3048 if unit in ('CFS','GPM','MGD') else 1.;volume=length**3
    flow={'CFS':28.316846592,'GPM':.0630901964,'MGD':43.8126363889,'CMS':1000.,'LPS':1.,'MLD':1000/86.4}[unit]
    opened=False
    try:
        solver.swmm_open(str(inp),str(folder/'native.rpt'),str(folder/'native.out'));opened=True;version=solver.swmm_get_version();solver.swmm_start(1)
        while solver.swmm_step()>0:pass
        flooding=0.;nonconverged=0
        for i in range(solver.project_get_count(E.ObjectType.NODE)):
            stats=solver.node_get_stats(i);flooding+=stats.volFlooded*volume;nonconverged+=stats.nonConvergedCount
        solver.swmm_end();runoff_error,routing_error,_=solver.swmm_get_mass_balance();solver.swmm_report();solver.swmm_close();opened=False
    finally:
        if opened:solver.swmm_close()
    h=output.init()
    try:
        output.open(h,str(folder/'native.out'));counts=output.get_proj_size(h);periods=output.get_times(h,E.Time.NUM_PERIODS)
        flow_max=0.;finalflows={}
        for i in range(counts[2]):
            series=output.get_link_series(h,i,E.LinkAttribute.FLOW_RATE,0,periods-1)
            if not all(math.isfinite(v) for v in series):raise ValueError('Nonfinite SWMM flow result')
            flow_max=max(flow_max,max(abs(v)*flow for v in series));finalflows[output.get_elem_name(h,E.ElementType.LINK,i)]=series[-1]*flow
    finally:output.close(h)
    checks=[compare('pinned_node_count',counts[1],c['expected']['node_count']),compare('pinned_link_count',counts[2],c['expected']['link_count']),
        compare('routing_continuity_within_limit',abs(routing_error)<=c['continuity_limit_pct'],True),compare('no_node_nonconvergence',nonconverged,0)]
    if 'final_link' in c['expected']:
        checks.append(compare('declared_steady_inflow_reaches_outfall_lps',finalflows[c['expected']['final_link']],c['expected']['final_flow_lps'],c['numeric_tolerance']))
    return dict(software_status='PASS' if all(r['status']=='PASS' for r in checks) else 'FAIL',comparisons=checks,
        issues=[r['check']+' failed; retain original source/settings and review timestep, boundaries and initialization' for r in checks if r['status']=='FAIL'],native_version=version,
        execution_input_sha256=hashlib.sha256(execution).hexdigest(),execution_changes=['Append explicit node/link/subcatchment reporting directives; source hydraulic parameters and event are unchanged'],
        source_flow_units=unit,normalized_flow_units='L/s',routing_continuity_error_pct=routing_error,runoff_continuity_error_pct=runoff_error,
        flooding_volume_m3=flooding,nonconverged_node_steps=nonconverged,maximum_absolute_flow_lps=flow_max,final_link_flows_lps=finalflows,
        coverage='Pinned external model native execution, input invariants and conservation; no automatic claim of field calibration, drainage-module equivalence or building-plumbing compliance')


def ifc(folder,c):
    from bim.model_intake import inspect_model
    inventory=inspect_model((folder/'model.dat').read_bytes(),'coordproof-mechanical-room.ifc')
    expected=list(csv.DictReader(io.StringIO((folder/'inventory.dat').read_text(encoding='utf-8-sig'))))
    supported={'IfcPipeSegment','IfcPipeFitting','IfcSanitaryTerminal','IfcPump','IfcTank','IfcValve'}
    expected=[(row['ifc_name'],row['ifc_class']) for row in expected if row['ifc_class'] in supported]
    actual=[(row['name'],row['source_class']) for row in inventory['objects']]
    checks=[compare('upstream_supported_semantic_inventory',sorted(actual),sorted(expected)),
        compare('source_millimetres_to_m',inventory['unit_evidence']['length_scale_to_m'],.001),
        compare('stable_ids_unique',len({r['source_id'] for r in inventory['objects']}),len(inventory['objects']))]
    # Declared source relations are structural evidence, not inferred hydraulic edges.
    portids={p['source_id'] for row in inventory['objects'] for p in row['ports']}
    unresolved=[edge for edge in inventory['connections'] if edge['from_port'] not in portids or edge['to_port'] not in portids]
    measured=sum(r['geometry_status']=='EXTRACTED' for r in inventory['objects'])
    issues=[]
    if measured<len(inventory['objects']):issues.append(str(len(inventory['objects'])-measured)+' objects have no supported measured Axis/IfcPolyline; hydraulic geometry remains unevaluated')
    if unresolved:issues.append(str(len(unresolved))+' declared port relations cross unsupported MEP classes; this is not a complete hydraulic topology')
    return dict(software_status='PASS' if all(r['status']=='PASS' for r in checks) else 'FAIL',comparisons=checks,issues=issues,
        supported_object_count=len(inventory['objects']),declared_connection_count=len(inventory['connections']),
        measured_axis_count=measured,unresolved_cross_scope_connections=len(unresolved),
        coverage='Upstream semantic CSV versus plumbing IFC adapter identities/classes/units; ports across unsupported MEP classes and unavailable axis geometry remain unevaluated',limitations=inventory['limitations'])


def main(folder):
    folder=Path(folder);request=json.loads((folder/'request.json').read_text());c=request['case']
    report={'epanet':lambda:epanet(folder,c,request.get('library')),'swmm':lambda:swmm(folder,c),'ifc':lambda:ifc(folder,c)}[c['runner']]()
    (folder/'result.json').write_text(json.dumps(report,allow_nan=False),encoding='utf-8')


if __name__=='__main__':main(sys.argv[1])
