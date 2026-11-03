"""Engineering audit of explicit pressure zones and supplied/native PDA reports.

This layer never edits delivered flow after hydraulic solution. Different zone
PDA parameters are flagged when the configured backend cannot represent them.
"""
import math
from engineering.common import fields,num,text,rows,unique,check,result
from solvers.graph import normalize_graph
from solvers.service import fingerprint


def pressure_zones(data):
    fields(data,'source_id model solver_report zones boundaries pressure_tolerance_m flow_tolerance_lps')
    ref=text(data,'source_id');model,topology=normalize_graph(data.get('model'))
    report=data.get('solver_report')
    if not isinstance(report,dict) or report.get('schema_version')!='pressure-network-result-1' or report.get('backend')!='epanet':raise ValueError('Pressure zones require an EPANET-format hydraulic report')
    if report.get('input_sha256')!=fingerprint(model) or report.get('normalized_model')!=model:raise ValueError('Hydraulic report is stale or its normalized network does not match the current model')
    ptol=num(data,'pressure_tolerance_m',positive=True,maximum=.01);qtol=num(data,'flow_tolerance_lps',positive=True,maximum=.01)
    zones=rows(data,'zones',limit=50);unique(zones);assignment={};nodeids={n['id'] for n in model['nodes']};checks=[];trace=[]
    byzone={z['id']:z for z in zones};profiles_match=True
    for z in zones:
        fields(z,'id source_id nodes minimum_supply_m maximum_supply_m minimum_delivered_fraction pda_minimum_m pda_required_m pda_exponent calibration_reference')
        source=text(z,'source_id');text(z,'calibration_reference')
        members=z.get('nodes')
        if not isinstance(members,list) or not members or any(not isinstance(n,str) or n not in nodeids for n in members):raise ValueError('Each zone needs explicit known node IDs')
        for n in members:
            if n in assignment:raise ValueError('Node is assigned more than once to pressure zones')
            assignment[n]=z['id']
        lo=num(z,'minimum_supply_m',minimum=0);hi=num(z,'maximum_supply_m',positive=True)
        if lo>hi:raise ValueError('Zone pressure envelope is reversed')
        num(z,'minimum_delivered_fraction',minimum=0,maximum=1)
        p0=num(z,'pda_minimum_m',minimum=0);p1=num(z,'pda_required_m',positive=True);exponent=num(z,'pda_exponent',positive=True,maximum=1)
        if p1<=p0:raise ValueError('Zone PDA requires full-service pressure above zero-service pressure')
        dm=model['demand_model']
        match=dm['type']!='PDA' or all(math.isclose(a,b,rel_tol=0,abs_tol=1e-10) for a,b in [(p0,dm['minimum_pressure_m']),(p1,dm['required_pressure_m']),(exponent,dm['exponent'])])
        profiles_match=profiles_match and match
        checks.append(check(z['id']+':backend_represents_zone_pda',match,dict(minimum=p0,required=p1,exponent=exponent),dm,'profile',source))
    if set(assignment)!=nodeids:raise ValueError('Every model node, including source/tank boundaries, must belong to exactly one zone')
    boundaries=rows(data,'boundaries',empty=True,limit=100);unique(boundaries,'link_id');links={e['id']:e for e in model['links']}
    bylink={b['link_id']:b for b in boundaries}
    cross={e['id'] for e in model['links'] if assignment[e['from_node']]!=assignment[e['to_node']]}
    if set(bylink)!=cross:raise ValueError('Boundary records must cover exactly the links crossing pressure zones')
    for boundary in boundaries:
        fields(boundary,'link_id source_id from_zone to_zone treatment reference');source=text(boundary,'source_id');text(boundary,'reference')
        e=links[boundary['link_id']];typ=boundary.get('treatment')
        okay=boundary.get('from_zone')==assignment[e['from_node']] and boundary.get('to_zone')==assignment[e['to_node']]
        if typ in ('PRV','PSV'):okay=okay and e['kind']=='valve' and e.get('valve_type')==typ
        elif typ=='booster':okay=okay and e['kind']=='pump'
        elif typ!='open_reviewed':raise ValueError('Boundary treatment must be PRV, PSV, booster or open_reviewed')
        checks.append(check(e['id']+':zone_boundary_mapping',okay,typ,e['kind']+' '+e.get('valve_type',''),'boundary',source))
    diagnostics=report.get('diagnostics',[])
    if not report.get('complete') or any(d.get('severity')=='ERROR' for d in diagnostics):
        return result(dict(reviewed_snapshots=0,minimum_service_fraction=None,maximum_pressure_m=None,solver_status=report.get('solver_status','UNKNOWN')),
            dict(reviewed_snapshots='count',minimum_service_fraction='1',maximum_pressure_m='m',solver_status='status'),checks,complete=False,
            notes=['Solver report incomplete/failed. Correct backend/convergence/connectivity diagnostics before zone engineering acceptance.'])
    snapshots=rows(report,'snapshots',limit=1000);maxp=-math.inf;minfrac=1.;worstconsistency=0.
    if len(snapshots)*len(nodeids)>30000:raise ValueError('Too many pressure-zone report rows; shorten the event or partition the review')
    for snapshot in snapshots:
        time=num(snapshot,'time_s',minimum=0)
        reported=rows(snapshot,'nodes',limit=500);unique(reported,'node_id')
        if {r['node_id'] for r in reported}!=nodeids:raise ValueError('Every hydraulic snapshot must cover every model node')
        for row in reported:
            identity=row['node_id'];zone=byzone[assignment[identity]];source=zone['source_id']
            original=next(n for n in model['nodes'] if n['id']==identity)
            p=num(row,'head_m')-original['elevation_m']
            if row.get('kind')!=original['kind']:raise ValueError('Snapshot node kind differs from normalized model')
            maxp=max(maxp,p);pressure_ok=zone['minimum_supply_m']-ptol<=p<=zone['maximum_supply_m']+ptol
            checks.append(check(identity+':zone_pressure@'+str(time),pressure_ok,p,[zone['minimum_supply_m'],zone['maximum_supply_m']],'m',source))
            if original['kind']!='junction':continue
            required=num(row,'requested_demand_lps',minimum=0);delivered=num(row,'delivered_demand_lps',minimum=-qtol)
            pattern=model['patterns'].get(original.get('demand_pattern'),[1]);mult=pattern[int(time//model['simulation']['pattern_step_s'])%len(pattern)]
            requested=original['demand_lps']*mult+original['fire_demand_lps']
            if abs(required-requested)>qtol:raise ValueError('Snapshot requested demand does not match the source demand model/pattern')
            dm=model['demand_model']
            expected=required
            if dm['type']=='PDA':
                ratio=max(0,min(1,(p-dm['minimum_pressure_m'])/(dm['required_pressure_m']-dm['minimum_pressure_m'])))
                expected=required*ratio**dm['exponent']
            discrepancy=abs(expected-delivered);worstconsistency=max(worstconsistency,discrepancy)
            fraction=delivered/required if required>qtol else 1.;minfrac=min(minfrac,fraction)
            checks.extend([check(identity+':demand_delivery@'+str(time),fraction+qtol/max(required,qtol)>=zone['minimum_delivered_fraction'],fraction,zone['minimum_delivered_fraction'],'1',source),
                check(identity+':solver_pda_consistency@'+str(time),discrepancy<=qtol,discrepancy,qtol,'L/s',source)])
            trace.append(dict(kind='zone_service',id=identity,zone=zone['id'],time_s=time,pressure_m=p,requested_lps=required,
                delivered_lps=delivered,delivered_fraction=fraction,pda_curve_expected_lps=expected,source_id=source))
    return result(dict(reviewed_snapshots=len(snapshots),minimum_service_fraction=minfrac,maximum_pressure_m=maxp,
        maximum_demand_curve_discrepancy_lps=worstconsistency,zone_pda_profiles_represented=profiles_match,solver_status=report.get('solver_status','UNKNOWN')),
        dict(reviewed_snapshots='count',minimum_service_fraction='1',maximum_pressure_m='m',maximum_demand_curve_discrepancy_lps='L/s',zone_pda_profiles_represented='boolean',solver_status='status'),checks,trace,complete=profiles_match,
        notes=['Audits a hash-matched normalized network and supplied EPANET-format report; report provenance is recorded, not cryptographically established. Use the native solve action to regenerate reports after model edits.',
            'Pressure envelopes, delivery fractions and calibrated PDA thresholds/exponents are explicit zone criteria. EPANET 2.2 uses one global PDA profile; differing zone curves are flagged as unrepresented, never patched into delivered flow after solution.',
            'Boundary mapping checks PRV/PSV/pump type and direction, not valve failure reliability or authority approval. Zero demand does not prove available flow capacity. DDA comparisons do not establish pressure-dependent service; commissioning/field calibration and min/max-source scenarios remain required.'])
