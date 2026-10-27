"""Explicit SI pressure-network contract and deterministic graph normalization."""
from copy import deepcopy
import math
import re


def number(value,name,minimum=None,maximum=None,positive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(name+' must be finite numeric data')
    if positive and value<=0 or minimum is not None and value<minimum or maximum is not None and value>maximum:raise ValueError(name+' is outside its supported range')
    return value


def text(value,name):
    if not isinstance(value,str) or not value.strip():raise ValueError(name+' requires a reference')
    return value


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,30}',value) or value=='PLM_FLAT':raise ValueError('IDs require 1–31 ASCII letters/digits/_/- starting with a letter; PLM_FLAT is reserved')
    return value


def keys(row,allowed,label):
    if not isinstance(row,dict):raise ValueError(label+' must be an object')
    extra=set(row)-set(allowed.split())
    if extra:raise ValueError(label+' has unsupported fields: '+', '.join(sorted(extra)))


def topology(nodes,links):
    parent={n:n for n in nodes};cycles=[];adj={n:set() for n in nodes}
    def find(a):
        while parent[a]!=a:a=parent[a]
        return a
    for edge in links:
        a,b=edge['from_node'],edge['to_node'];ra,rb=find(a),find(b)
        if ra==rb:cycles.append(edge['id'])
        else:parent[rb]=ra
        adj[a].add(b);adj[b].add(a)
    groups={}
    for n in nodes:groups.setdefault(find(n),[]).append(n)
    return dict(has_loops=bool(cycles),cycle_closing_links=cycles,components=list(groups.values()))


def normalize_graph(model):
    keys(model,'schema_version units code_id basis_reference nodes links curves patterns controls simulation demand_model scenarios','Network')
    if model.get('schema_version')!='pressure-network-1' or model.get('units')!='SI':raise ValueError('General network requires schema_version=pressure-network-1 and units=SI')
    m=deepcopy(model);text(m.get('basis_reference'),'Network basis')
    for group,limit in [('nodes',500),('links',1000),('controls',100)]:
        values=m.setdefault(group,[])
        if not isinstance(values,list) or len(values)>limit or group!='controls' and not values:raise ValueError(group+' is empty, invalid or exceeds its supported object limit')
    nodes={};links={}
    for n in m['nodes']:
        keys(n,'id kind elevation_m head_m demand_lps fire_demand_lps demand_pattern required_pressure_m demand_reference initial_level_m min_level_m max_level_m diameter_m min_volume_m3 reference','Node')
        nid=identifier(n.get('id'))
        if nid in nodes:raise ValueError('Duplicate node '+nid)
        nodes[nid]=n;kind=n.get('kind');text(n.get('reference'),'Node '+nid)
        number(n.get('elevation_m'),'elevation_m')
        if kind=='junction':
            number(n.setdefault('demand_lps',0),'demand_lps',minimum=0)
            number(n.setdefault('fire_demand_lps',0),'fire_demand_lps',minimum=0)
            number(n.get('required_pressure_m'),'required_pressure_m',minimum=0)
            if n['demand_lps'] or n['fire_demand_lps']:text(n.get('demand_reference'),'Junction demand '+nid)
            if any(k in n for k in ('head_m','initial_level_m','min_level_m','max_level_m','diameter_m','min_volume_m3')):raise ValueError('Junction has source/tank properties: '+nid)
        elif kind=='source':
            number(n.get('head_m'),'absolute source head_m')
            if any(k in n for k in ('demand_lps','fire_demand_lps','demand_pattern','initial_level_m','min_level_m','max_level_m','diameter_m','min_volume_m3')):raise ValueError('Source has junction/tank properties: '+nid)
        elif kind=='tank':
            for name in ('initial_level_m','min_level_m','max_level_m'):number(n.get(name),name,minimum=0)
            if not n['min_level_m']<=n['initial_level_m']<=n['max_level_m'] or n['max_level_m']<=n['min_level_m']:raise ValueError('Tank levels require min <= initial <= max, with max > min: '+nid)
            number(n.get('diameter_m'),'tank diameter_m',positive=True);number(n.setdefault('min_volume_m3',0),'min_volume_m3',minimum=0)
            if any(k in n for k in ('head_m','demand_lps','fire_demand_lps','demand_pattern')):raise ValueError('Tank has source/junction properties: '+nid)
        else:raise ValueError('Node kind must be junction, source or tank')
    curves=m.setdefault('curves',{});patterns=m.setdefault('patterns',{})
    if not isinstance(curves,dict) or len(curves)>100 or not isinstance(patterns,dict) or len(patterns)>100:raise ValueError('Curve/pattern maps exceed supported limits')
    for cid,curve in curves.items():
        identifier(cid);keys(curve,'points reference','Pump curve');text(curve.get('reference'),'Pump curve '+cid)
        points=curve.get('points')
        if not isinstance(points,list) or not 3<=len(points)<=100:raise ValueError('Pump H-Q curve needs 3–100 explicit points')
        lastq=-1;lasth=math.inf
        for p in points:
            keys(p,'flow_lps head_m','Pump curve point');q=number(p.get('flow_lps'),'curve flow_lps',minimum=0);h=number(p.get('head_m'),'curve head_m',minimum=0)
            if q<=lastq or h>=lasth:raise ValueError('Pump curve flow must increase and head decrease strictly')
            lastq,lasth=q,h
    for pid,values in patterns.items():
        identifier(pid)
        if not isinstance(values,list) or not 1<=len(values)<=1000:raise ValueError('Demand pattern needs 1–1000 multipliers')
        for v in values:number(v,'demand pattern multiplier',minimum=0)
    for n in nodes.values():
        if n.get('demand_pattern') not in (None,*patterns):raise ValueError('Unknown demand pattern on '+n['id'])
    for edge in m['links']:
        keys(edge,'id kind from_node to_node length_m internal_mm roughness roughness_unit minor_loss_k status curve_id speed valve_type setting setting_unit reference','Link')
        eid=identifier(edge.get('id'))
        if eid in links:raise ValueError('Duplicate link '+eid)
        links[eid]=edge;text(edge.get('reference'),'Link '+eid)
        a,b=edge.get('from_node'),edge.get('to_node')
        if a not in nodes or b not in nodes or a==b:raise ValueError('Unknown/self-connected endpoints on '+eid)
        kind=edge.get('kind');status=edge.setdefault('status','ACTIVE' if kind=='valve' else 'OPEN')
        if status not in ('OPEN','CLOSED') and not (kind=='valve' and status=='ACTIVE'):raise ValueError('Invalid initial link status '+eid)
        if kind=='pipe':
            number(edge.get('length_m'),'pipe length_m',positive=True);number(edge.get('internal_mm'),'actual bore internal_mm',positive=True)
            number(edge.get('roughness'),'pipe roughness',positive=True);number(edge.setdefault('minor_loss_k',0),'minor_loss_k',minimum=0)
            if edge['length_m']+1e-9<abs(nodes[a]['elevation_m']-nodes[b]['elevation_m']):raise ValueError('Pipe length shorter than elevation rise: '+eid)
            if any(k in edge for k in ('curve_id','speed','valve_type','setting','setting_unit')):raise ValueError('Pipe has pump/valve properties '+eid)
        elif kind=='pump':
            if edge.get('curve_id') not in curves:raise ValueError('Pump requires a referenced H-Q curve: '+eid)
            number(edge.setdefault('speed',1),'relative pump speed',positive=True)
            if any(k in edge for k in ('length_m','internal_mm','roughness','minor_loss_k','valve_type','setting','setting_unit')):raise ValueError('Pump has pipe/valve properties '+eid)
        elif kind=='valve':
            vt=edge.get('valve_type');unit={'PRV':'m','PSV':'m','PBV':'m','FCV':'L/s','TCV':'-'}.get(vt)
            if unit is None:raise ValueError('Supported valve types: PRV, PSV, PBV, FCV, TCV')
            if edge.get('setting_unit')!=unit:raise ValueError('Valve setting unit must be '+unit+' for '+vt)
            number(edge.get('setting'),'valve setting',minimum=0);number(edge.get('internal_mm'),'valve internal_mm',positive=True);number(edge.setdefault('minor_loss_k',0),'minor_loss_k',minimum=0)
            if any(k in edge for k in ('length_m','roughness','curve_id','speed')):raise ValueError('Valve has pipe/pump properties '+eid)
        else:raise ValueError('Link kind must be pipe, pump or valve')
    for control in m['controls']:
        keys(control,'link_id status condition node_id relation value time_s reference','Control')
        text(control.get('reference'),'Control')
        if control.get('link_id') not in links or control.get('status') not in ('OPEN','CLOSED'):raise ValueError('Control requires an existing link and OPEN/CLOSED status')
        if control.get('condition')=='elapsed_time':
            number(control.get('time_s'),'control time_s',minimum=0,maximum=604800)
            if type(control['time_s']) is not int:raise ValueError('Control time_s must be integer seconds')
            if any(k in control for k in ('node_id','relation','value')):raise ValueError('Time control cannot contain a node threshold')
        elif control.get('condition')=='node_threshold':
            if control.get('node_id') not in nodes or nodes[control['node_id']]['kind']=='source' or control.get('relation') not in ('ABOVE','BELOW'):raise ValueError('Threshold control requires a tank/junction and ABOVE/BELOW')
            number(control.get('value'),'threshold metres',minimum=0)
            if 'time_s' in control:raise ValueError('Node threshold control cannot contain time_s')
        else:raise ValueError('Supported controls use elapsed_time or node_threshold')
    sim=m.setdefault('simulation',{});keys(sim,'duration_s hydraulic_step_s pattern_step_s headloss trials accuracy','Simulation')
    for name,default,low,high in [('duration_s',0,0,604800),('hydraulic_step_s',3600,60,86400),('pattern_step_s',3600,60,86400),('trials',100,1,1000)]:
        value=sim.setdefault(name,default);number(value,name,minimum=low,maximum=high)
        if type(value) is not int:raise ValueError(name+' requires integer seconds/count')
    if sim['duration_s']//sim['hydraulic_step_s']>2000:raise ValueError('Too many hydraulic intervals; increase timestep or shorten duration')
    if sim.setdefault('headloss','H-W') not in ('H-W','D-W','C-M'):raise ValueError('Headloss must be H-W, D-W or C-M; roughness units follow that explicit equation')
    for edge in links.values():
        if edge['kind']=='pipe' and edge.get('roughness_unit')!={'H-W':'C','D-W':'mm','C-M':'s/m^(1/3)'}[sim['headloss']]:raise ValueError('Pipe roughness_unit must match the explicit headloss equation (C, mm, or s/m^(1/3))')
    number(sim.setdefault('accuracy',.000001),'relative hydraulic accuracy',positive=True,maximum=.01)
    demand=m.setdefault('demand_model',{'type':'DDA','reference':'Demand-driven specified design envelope'})
    keys(demand,'type minimum_pressure_m required_pressure_m exponent reference','Demand model');text(demand.get('reference'),'Demand model')
    if demand.get('type')=='PDA':
        number(demand.get('minimum_pressure_m'),'PDA minimum_pressure_m',minimum=0);number(demand.get('required_pressure_m'),'PDA required_pressure_m',positive=True);number(demand.get('exponent'),'PDA exponent',positive=True)
        if demand['required_pressure_m']<=demand['minimum_pressure_m']:raise ValueError('PDA required pressure must exceed minimum pressure')
    elif demand.get('type')!='DDA' or any(k in demand for k in ('minimum_pressure_m','required_pressure_m','exponent')):raise ValueError('Use DDA without PDA parameters, or explicit PDA parameters')
    topo=topology(nodes,m['links'])
    for component in topo['components']:
        if not any(nodes[n]['kind'] in ('source','tank') for n in component):raise ValueError('Component has no source/tank: '+', '.join(component))
    if not any(n['kind']=='junction' for n in nodes.values()):raise ValueError('At least one junction is required')
    scenarios=m.setdefault('scenarios',[])
    if not isinstance(scenarios,list) or len(scenarios)>10:raise ValueError('At most ten scenario overlays are supported')
    seen=set()
    for scenario in scenarios:
        validate_scenario(scenario,nodes,links)
        if scenario['id'] in seen:raise ValueError('Duplicate scenario ID')
        seen.add(scenario['id'])
    return m,topo


def validate_scenario(s,nodes,links):
    keys(s,'id label reference demand_multiplier source_heads_m fire_demands_lps tank_levels_m unavailable_links','Scenario')
    identifier(s.get('id'));text(s.get('label'),'Scenario label');text(s.get('reference'),'Scenario')
    number(s.get('demand_multiplier',1),'scenario demand multiplier',minimum=0)
    for group,kind,minimum in [('source_heads_m','source',None),('fire_demands_lps','junction',0),('tank_levels_m','tank',0)]:
        values=s.get(group,{})
        if not isinstance(values,dict):raise ValueError(group+' must be a mapping')
        for nid,value in values.items():
            if nid not in nodes or nodes[nid]['kind']!=kind:raise ValueError('Scenario '+group+' has wrong/unknown target '+nid)
            number(value,group,minimum=minimum)
            if kind=='tank' and not nodes[nid]['min_level_m']<=value<=nodes[nid]['max_level_m']:raise ValueError('Scenario tank level outside declared bounds')
    unavailable=s.get('unavailable_links',[])
    if not isinstance(unavailable,list) or any(e not in links for e in unavailable) or len(set(unavailable))!=len(unavailable):raise ValueError('Unavailable link IDs must be unique known links')


def apply_scenario(model,scenario):
    m,_=normalize_graph(model);nodes={n['id']:n for n in m['nodes']};links={l['id']:l for l in m['links']};validate_scenario(scenario,nodes,links)
    for n in nodes.values():
        if n['kind']=='junction':n['demand_lps']*=scenario.get('demand_multiplier',1)
    for key,field in [('source_heads_m','head_m'),('tank_levels_m','initial_level_m')]:
        for nid,value in scenario.get(key,{}).items():nodes[nid][field]=value
    for nid,value in scenario.get('fire_demands_lps',{}).items():nodes[nid]['fire_demand_lps']+=value
    unavailable=scenario.get('unavailable_links',[])
    for eid in unavailable:links[eid]['status']='CLOSED'
    disabled=[c for c in m['controls'] if c['link_id'] in unavailable]
    m['controls']=[c for c in m['controls'] if c['link_id'] not in unavailable]
    m['scenarios']=[]
    normalized,_=normalize_graph(m)
    return normalized,disabled
