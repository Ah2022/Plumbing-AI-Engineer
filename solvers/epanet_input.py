"""Serialize only normalized typed data; raw EPANET commands are never accepted."""
from solvers.graph import normalize_graph


def clock(seconds):
    return f'{seconds//3600}:{seconds%3600//60:02d}:{seconds%60:02d}'


def build_input(model):
    m,_=normalize_graph(model);lines=['[TITLE]','Plumbing engineering simulation - review required','[JUNCTIONS]']
    nodes=m['nodes'];links=m['links'];sim=m['simulation'];demand=m['demand_model']
    lines += [f"{n['id']} {n['elevation_m']} 0" for n in nodes if n['kind']=='junction']
    lines += ['[RESERVOIRS]']+[f"{n['id']} {n['head_m']}" for n in nodes if n['kind']=='source']
    lines += ['[TANKS]']+[f"{n['id']} {n['elevation_m']} {n['initial_level_m']} {n['min_level_m']} {n['max_level_m']} {n['diameter_m']} {n['min_volume_m3']}" for n in nodes if n['kind']=='tank']
    lines += ['[PIPES]']+[f"{p['id']} {p['from_node']} {p['to_node']} {p['length_m']} {p['internal_mm']} {p['roughness']} {p['minor_loss_k']} {p['status']}" for p in links if p['kind']=='pipe']
    lines += ['[PUMPS]']+[f"{p['id']} {p['from_node']} {p['to_node']} HEAD {p['curve_id']} SPEED {p['speed']}" for p in links if p['kind']=='pump']
    lines += ['[VALVES]']+[f"{v['id']} {v['from_node']} {v['to_node']} {v['internal_mm']} {v['valve_type']} {v['setting']} {v['minor_loss_k']}" for v in links if v['kind']=='valve']
    # OPEN on a pump resets its speed to1 in EPANET; preserve explicit SPEED.
    lines += ['[STATUS]']+[f"{e['id']} {e['status']}" for e in links if e['kind']=='pump' and e['status']=='CLOSED' or e['kind']=='valve' and e['status']!='ACTIVE']
    lines += ['[CURVES]']+[f"{cid} {p['flow_lps']} {p['head_m']}" for cid,curve in m['curves'].items() for p in curve['points']]
    lines += ['[PATTERNS]','PLM_FLAT 1']
    for pid,values in m['patterns'].items():
        lines += [pid+' '+' '.join(str(v) for v in values[i:i+8]) for i in range(0,len(values),8)]
    lines += ['[DEMANDS]']
    for n in nodes:
        if n['kind']=='junction':
            lines.append(f"{n['id']} {n['demand_lps']} {n.get('demand_pattern') or 'PLM_FLAT'} BASE")
            if n['fire_demand_lps']:lines.append(f"{n['id']} {n['fire_demand_lps']} PLM_FLAT FIRE")
    lines += ['[CONTROLS]']
    for control in m['controls']:
        target=next(e for e in links if e['id']==control['link_id'])
        setting=target['speed'] if target['kind']=='pump' and control['status']=='OPEN' else control['status']
        line=f"LINK {control['link_id']} {setting}"
        if control['condition']=='elapsed_time':line+=' AT TIME '+clock(control['time_s'])
        else:line+=f" IF NODE {control['node_id']} {control['relation']} {control['value']}"
        lines.append(line)
    lines += ['[OPTIONS]','UNITS LPS','HEADLOSS '+sim['headloss'],'DEMAND MODEL '+demand['type'],'PATTERN PLM_FLAT',
              'TRIALS '+str(sim['trials']),'ACCURACY '+str(sim['accuracy']),'UNBALANCED STOP']
    if demand['type']=='PDA':lines += [f"MINIMUM PRESSURE {demand['minimum_pressure_m']}",f"REQUIRED PRESSURE {demand['required_pressure_m']}",f"PRESSURE EXPONENT {demand['exponent']}"]
    lines += ['[TIMES]','DURATION '+clock(sim['duration_s']),'HYDRAULIC TIMESTEP '+clock(sim['hydraulic_step_s']),
        'PATTERN TIMESTEP '+clock(sim['pattern_step_s']),'REPORT TIMESTEP '+clock(sim['hydraulic_step_s']),
        '[REPORT]','STATUS FULL','[END]']
    return '\n'.join(lines)+'\n'
