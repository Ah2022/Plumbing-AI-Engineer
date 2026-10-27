"""Independent worksheet arithmetic. Never import production calculation code.

Candidate references are author-prepared, not independently engineer-approved.
Golden files are frozen inputs to tests; this module cannot overwrite them.
"""
from decimal import Decimal, localcontext
import math

G = Decimal('9.80665')
PI = Decimal('3.1415926535897932384626433832795028841971693993751')


def hydraulic_row(q_lps, bore_mm, length_m, c, k):
    with localcontext() as ctx:
        ctx.prec = 45
        q, d, length, c, k = map(lambda x: Decimal(str(x)), (q_lps,bore_mm,length_m,c,k))
        q /= 1000; d /= 1000
        v = q / (PI*d*d/4)
        friction = Decimal('10.67')*length*q**Decimal('1.852')/(c**Decimal('1.852')*d**Decimal('4.8704'))
        minor = k*v*v/(2*G)
        return dict(flow_lps=float(q*1000),internal_mm=float(d*1000),velocity_m_s=float(v),
                    friction_loss_m=float(friction),fitting_loss_m=float(minor))


def project_worksheet(project):
    """Use independently declared paths/demands, not a traversal of engine output."""
    model=project['water_model']; catalogue={s['size_id']:s for s in model['catalogues']['REFERENCE']}
    pipes={p['id']:p for p in model['pipes']};nodes={n['id']:n for n in model['nodes']}
    expected={}
    for pid,q in project['hand_schedule']['pipe_flows_lps'].items():
        p=pipes[pid]; size=catalogue[p['selected_size_id']]
        row=hydraulic_row(q,size['internal_mm'],p['length_m'],model['materials']['REFERENCE']['c_factor'],p['fittings_k'])
        row.update(nominal_mm=size['nominal_mm'],selected_size_id=size['size_id'],equipment_loss_m=p['equipment_loss_m'])
        expected[pid]=row
    terminals={}
    for tid,path in project['hand_schedule']['terminal_paths'].items():
        node=nodes[tid]
        losses=sum(expected[p]['friction_loss_m']+expected[p]['fitting_loss_m']+expected[p]['equipment_loss_m'] for p in path)
        pressure=model['available_head_m']-(node['elevation_m']-nodes[model['root']]['elevation_m'])-losses
        terminals[tid]=dict(available_head_m=pressure,required_head_m=node['required_residual_head_m'],margin_m=pressure-node['required_residual_head_m'],path=path)
    governing=min(terminals,key=lambda k:(terminals[k]['margin_m'],k))
    okay=all(t['margin_m']>=0 for t in terminals.values()) and all(p['velocity_m_s']<=model['velocity_limit_m_s'] for p in expected.values())
    s=project['systems']
    return dict(pipes=expected,terminals=terminals,governing_terminal=governing,
        minimum_pressure_margin_m=terminals[governing]['margin_m'],technical_status='PASS' if okay else 'FAIL',
        review_status='REVIEW_REQUIRED',
        heater_kw=s['heater_mass_flow_kg_s']*4.186*(s['hot_c']-s['cold_c']),
        domestic_storage_m3=s['average_demand_lps']*s['storage_hours']*3.6*(1+s['storage_margin_pct']/100),
        pump_power_kw=s['pump_flow_lps']*9.80665*sum(s['pump_head_components_m'])/(s['pump_efficiency']*1000),
        storm_flow_lps=s['runoff_coefficient']*s['rainfall_mm_hr']*s['roof_area_m2']/3600,
        drainage=project['hand_schedule']['drainage_expected'],
        expected_warnings=project['expected_warnings'],unevaluated_checks=project['unevaluated_checks'])


def epanet_input(project):
    """DDA, steady state, H-W; no pumps/valves/control or diversity assumptions."""
    m=project['water_model'];sizes={s['size_id']:s for s in m['catalogues']['REFERENCE']}
    if any(p['equipment_loss_m'] for p in m['pipes']):
        raise ValueError('Fixed equipment head loss requires an explicit EPANET mapping')
    root=next(n for n in m['nodes'] if n['id']==m['root'])
    lines=['[TITLE]',project['project_id']+' - authored validation candidate, not approved','[JUNCTIONS]',';ID Elevation_m Demand_LPS']
    lines += [f"{n['id']} {n['elevation_m']} {n.get('design_flow_lps',0)}" for n in m['nodes'] if n['id']!=m['root']]
    lines += ['[RESERVOIRS]',f"{m['root']} {m['available_head_m']+root['elevation_m']}",'[PIPES]',';ID From To Length_m Internal_mm C MinorK']
    lines += [f"{p['id']} {p['from_node']} {p['to_node']} {p['length_m']} {sizes[p['selected_size_id']]['internal_mm']} {m['materials']['REFERENCE']['c_factor']} {p['fittings_k']} OPEN" for p in m['pipes']]
    lines += ['[OPTIONS]','UNITS LPS','HEADLOSS H-W','DEMAND MODEL DDA','ACCURACY 0.000001','TRIALS 100','[TIMES]','DURATION 0','[REPORT]','STATUS YES','NODES ALL','LINKS ALL','[END]']
    return '\n'.join(lines)+'\n'


def epanet_convention_pressures(project):
    """Explain 2.2 conventions from its published source, not fitted tolerances.

    hydcoeffs.c uses 4.727, d^4.871 in ft/cfs; input1.c uses
    0.02517*K/d^4; types.h uses 28.317 L/cuft and 0.3048 m/ft.
    """
    m=project['water_model'];sizes={r['size_id']:r for r in m['catalogues']['REFERENCE']}
    losses={}
    for p in m['pipes']:
        q=project['hand_schedule']['pipe_flows_lps'][p['id']]/28.317
        d=sizes[p['selected_size_id']]['internal_mm']/304.8
        l=p['length_m']/.3048;c=m['materials']['REFERENCE']['c_factor']
        losses[p['id']]=.3048*(4.727*l*q**1.852/(c**1.852*d**4.871)+.02517*p['fittings_k']*q*q/d**4)
    elevations={n['id']:n['elevation_m'] for n in m['nodes']}
    return {tid:m['available_head_m']-(elevations[tid]-elevations[m['root']])-sum(losses[p] for p in path)
            for tid,path in project['hand_schedule']['terminal_paths'].items()}
