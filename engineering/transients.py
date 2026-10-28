"""Elastic liquid network method of characteristics; stop at vapour pressure."""
import math
from engineering.common import fields, num, text, rows, unique, check, result, G, interpolate


def _lerp(values, x):
    left=min(len(values)-2,max(0,int(x))); f=x-left
    return values[left]*(1-f)+values[left+1]*f


def network_transient(data):
    fields(data,'source_id density_kg_m3 atmospheric_kpa vapour_absolute_kpa allowable_gauge_kpa '
        'duration_s maximum_step_s report_step_s initial_tolerance_m nodes pipes')
    ref=text(data,'source_id'); rho=num(data,'density_kg_m3',positive=True)
    atm=num(data,'atmospheric_kpa',positive=True); vapour=num(data,'vapour_absolute_kpa',minimum=0)
    allowable=num(data,'allowable_gauge_kpa',positive=True)
    duration=num(data,'duration_s',positive=True,maximum=120)
    maxdt=num(data,'maximum_step_s',positive=True,maximum=1)
    report=num(data,'report_step_s',positive=True)
    tol=num(data,'initial_tolerance_m',positive=True,maximum=.01)
    nodes=rows(data,'nodes',limit=50); pipes=rows(data,'pipes',limit=50); unique(nodes); unique(pipes)
    bynode={}; incoming={}; outgoing={}; valvepoints={}
    for n in nodes:
        fields(n,'id source_id kind elevation_m initial_head_m fixed_head_m demand_lps downstream_head_m valve_resistance_m_per_m6_s2 opening')
        identity=text(n,'id'); text(n,'source_id'); num(n,'elevation_m'); num(n,'initial_head_m')
        if n.get('kind') not in ('fixed_head','junction','valve'): raise ValueError('Transient node kind must be fixed_head, junction or valve')
        if n['kind']=='fixed_head':
            if abs(num(n,'fixed_head_m')-n['initial_head_m'])>tol: raise ValueError('Initial head must match fixed-head boundary')
        elif n['kind']=='junction': num(n,'demand_lps',minimum=0)
        else:
            num(n,'downstream_head_m'); num(n,'valve_resistance_m_per_m6_s2',positive=True)
            points=rows(n,'opening',limit=200)
            for p in points:
                fields(p,'time_s fraction'); num(p,'time_s',minimum=0,maximum=duration); num(p,'fraction',minimum=0,maximum=1)
            if points[0]['time_s']!=0 or points[-1]['time_s']!=duration or any(b['time_s']<=a['time_s'] for a,b in zip(points,points[1:])):
                raise ValueError('Valve opening must cover the event with strictly increasing times; fraction defines flow coefficient, not stem travel')
            valvepoints[identity]=points
        bynode[identity]=n; incoming[identity]=[]; outgoing[identity]=[]
    if not any(n['kind']=='fixed_head' for n in nodes): raise ValueError('At least one fixed-head liquid boundary is required')
    state={}; dt=maxdt; neighbours={n:set() for n in bynode}
    for p in pipes:
        fields(p,'id source_id from_node to_node length_m internal_mm wave_speed_m_s friction_factor initial_flow_lps cells')
        identity=text(p,'id'); text(p,'source_id'); a=text(p,'from_node'); b=text(p,'to_node')
        if a not in bynode or b not in bynode or a==b: raise ValueError('Pipe endpoints must be different existing transient nodes')
        length=num(p,'length_m',positive=True); d=num(p,'internal_mm',positive=True)/1000
        speed=num(p,'wave_speed_m_s',positive=True); f=num(p,'friction_factor',minimum=0,maximum=1)
        q=num(p,'initial_flow_lps')/1000; nc=num(p,'cells',minimum=2,maximum=200)
        if int(nc)!=nc: raise ValueError('Transient cell count must be an integer')
        nc=int(nc); area=math.pi*d*d/4; bchar=speed/(G*area); dx=length/nc
        dt=min(dt,dx/speed)
        ha=bynode[a]['initial_head_m']; hb=bynode[b]['initial_head_m']
        loss=f*length/d*q*abs(q)/(2*G*area**2)
        if abs(ha-hb-loss)>tol: raise ValueError('Initial steady friction/head mismatch in '+identity+'; supply converged steady heads and flows')
        state[identity]=dict(H=[ha+(hb-ha)*j/nc for j in range(nc+1)],Q=[q]*(nc+1),B=bchar,dx=dx,speed=speed,d=d,A=area,f=f,a=a,b=b)
        incoming[b].append(identity); outgoing[a].append(identity); neighbours[a].add(b); neighbours[b].add(a)
    seeds={n['id'] for n in nodes if n['kind']=='fixed_head'}; todo=list(seeds)
    for n in todo:
        for other in neighbours[n]-seeds: seeds.add(other); todo.append(other)
    if seeds!=set(bynode): raise ValueError('Every transient component needs a fixed-head boundary')
    def external(n,t):
        if n['kind']=='junction': return n['demand_lps']/1000
        if n['kind']=='fixed_head': return None
        opening=interpolate(valvepoints[n['id']],t,'time_s','fraction'); delta=n['initial_head_m']-n['downstream_head_m']
        return opening*math.copysign(math.sqrt(abs(delta)/n['valve_resistance_m_per_m6_s2']),delta)
    for n in nodes:
        if not incoming[n['id']] and not outgoing[n['id']]: raise ValueError('Isolated transient node')
        flow=sum(state[p]['Q'][-1] for p in incoming[n['id']])-sum(state[p]['Q'][0] for p in outgoing[n['id']])
        target=external(n,0)
        if target is not None and abs(flow-target)>1e-8: raise ValueError('Initial flow continuity/valve coefficient mismatch at '+n['id'])
    updates=sum(len(s['H']) for s in state.values())*math.ceil(duration/dt)
    if updates>3000000 or (len(nodes)+len(pipes))*duration/report>50000:
        raise ValueError('Transient exceeds numerical/output bounds; shorten event, reduce cells or increase report interval')
    maximum=-float('inf'); minimum=float('inf'); stopped=False; trace=[]; t=0.; nextreport=0.
    def observe(time,save):
        nonlocal maximum,minimum,stopped
        for p,s in state.items():
            za=bynode[s['a']]['elevation_m']; zb=bynode[s['b']]['elevation_m']; count=len(s['H'])-1
            pressures=[rho*G*(h-(za+(zb-za)*j/count))/1000 for j,h in enumerate(s['H'])]
            maximum=max(maximum,max(pressures)); minimum=min(minimum,min(pressures)+atm)
            if min(pressures)+atm<=vapour: stopped=True
            if save: trace.append(dict(kind='pipe',id=p,time_s=time,minimum_absolute_kpa=min(pressures)+atm,
                maximum_gauge_kpa=max(pressures),from_flow_lps=s['Q'][0]*1000,to_flow_lps=s['Q'][-1]*1000))
        if save:
            for n in nodes:
                identity=n['id']; h=state[incoming[identity][0]]['H'][-1] if incoming[identity] else state[outgoing[identity][0]]['H'][0]
                trace.append(dict(kind='node',id=identity,time_s=time,head_m=h,gauge_kpa=rho*G*(h-n['elevation_m'])/1000))
    observe(0,True)
    if stopped: raise ValueError('Initial state reaches vapour pressure; a single-phase elastic transient cannot start')
    nextreport=report
    while t<duration-1e-12:
        step=min(dt,duration-t); new={}; cp_end={}; cm_start={}
        for p,s in state.items():
            h=s['H']; q=s['Q']; nc=len(h)-1; ratio=s['speed']*step/s['dx']
            resist=s['f']*s['speed']*step/(2*G*s['d']*s['A']**2)
            def plus(x):
                qi=_lerp(q,x); return _lerp(h,x)+s['B']*qi-resist*qi*abs(qi)
            def minus(x):
                qi=_lerp(q,x); return _lerp(h,x)-s['B']*qi+resist*qi*abs(qi)
            hn=[0.]*(nc+1); qn=[0.]*(nc+1)
            for j in range(1,nc):
                cp=plus(j-ratio); cm=minus(j+ratio); hn[j]=(cp+cm)/2; qn[j]=(cp-cm)/(2*s['B'])
            cp_end[p]=plus(nc-ratio); cm_start[p]=minus(ratio); new[p]=(hn,qn)
        for identity,n in bynode.items():
            coeff=sum(1/state[p]['B'] for p in incoming[identity]+outgoing[identity])
            rhs=sum(cp_end[p]/state[p]['B'] for p in incoming[identity])+sum(cm_start[p]/state[p]['B'] for p in outgoing[identity])
            if n['kind']=='fixed_head': head=n['fixed_head_m']
            elif n['kind']=='junction': head=(rhs-n['demand_lps']/1000)/coeff
            else:
                opening=interpolate(valvepoints[identity],t+step,'time_s','fraction')
                b=opening/math.sqrt(n['valve_resistance_m_per_m6_s2']); residual=rhs-coeff*n['downstream_head_m']
                y=2*abs(residual)/(b+math.sqrt(b*b+4*coeff*abs(residual))) if residual else 0.
                head=n['downstream_head_m']+math.copysign(y*y,residual)
            for p in incoming[identity]: new[p][0][-1]=head; new[p][1][-1]=(cp_end[p]-head)/state[p]['B']
            for p in outgoing[identity]: new[p][0][0]=head; new[p][1][0]=(head-cm_start[p])/state[p]['B']
        for p in state: state[p]['H'],state[p]['Q']=new[p]
        t+=step; save=t+1e-10>=nextreport or t+1e-10>=duration
        observe(t,save)
        if save: nextreport+=report
        if stopped:
            if not save: observe(t,True)
            break
    return result(dict(maximum_gauge_kpa=maximum,minimum_absolute_kpa=minimum,simulated_duration_s=t,
        time_step_s=dt,cavitation_domain_exceeded=stopped),
        dict(maximum_gauge_kpa='kPa gauge',minimum_absolute_kpa='kPa absolute',simulated_duration_s='s',time_step_s='s',cavitation_domain_exceeded='boolean'),
        [check('pressure_rating',maximum<=allowable,maximum,allowable,'kPa gauge',ref),
         check('single_phase_validity',not stopped,minimum,vapour,'kPa absolute',ref)],trace,complete=not stopped,
        notes=['Interpolated method of characteristics for constant-bore elastic liquid pipes, fixed-head boundaries, continuity junctions and tabulated valve flow-coefficient fractions. Quasi-steady Darcy friction; initial steady state must be supplied.',
            'Stops at first vapour-pressure crossing; results beyond that time are unevaluated. No column separation, entrained air, unsteady friction, pump inertia, surge-vessel or fluid-structure interaction model.',
            'Report samples may miss peaks; pressure extrema include every computational cell and step. Review timestep/grid convergence and real wave speeds before engineering acceptance.'])
