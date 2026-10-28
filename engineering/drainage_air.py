"""Lumped small-signal drainage-air network with one-way AAVs and forced traps.

Air displacement hydrographs must be supplied independently. This is not a
vertical two-phase stack solver or a code vent-sizing replacement.
"""
import math
from engineering.common import fields,num,text,rows,unique,check,result,G,interpolate


def _solve(matrix,rhs):
    n=len(rhs); a=[r[:]+[b] for r,b in zip(matrix,rhs)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda j:abs(a[j][col])); a[col],a[pivot]=a[pivot],a[col]
        if abs(a[col][col])<1e-20: raise ValueError('Air-network matrix is singular; review volumes and atmospheric paths')
        for j in range(col+1,n):
            factor=a[j][col]/a[col][col]
            for k in range(col,n+1): a[j][k]-=factor*a[col][k]
    out=[0.]*n
    for j in reversed(range(n)): out[j]=(a[j][-1]-sum(a[j][k]*out[k] for k in range(j+1,n)))/a[j][j]
    return out


def drainage_air(data):
    fields(data,'source_id atmospheric_kpa air_exponent maximum_pressure_ratio allowable_positive_pa allowable_negative_pa '
        'duration_s step_s report_step_s nodes vents displacements traps')
    ref=text(data,'source_id'); atm=num(data,'atmospheric_kpa',positive=True)*1000
    exponent=num(data,'air_exponent',minimum=1,maximum=1.67)
    fraction=num(data,'maximum_pressure_ratio',positive=True,maximum=.05)
    positive=num(data,'allowable_positive_pa',positive=True); negative=num(data,'allowable_negative_pa',positive=True)
    duration=num(data,'duration_s',positive=True,maximum=3600); step=num(data,'step_s',positive=True,maximum=1)
    report=num(data,'report_step_s',positive=True)
    nodes=rows(data,'nodes',limit=20); unique(nodes); ids={n['id']:i for i,n in enumerate(nodes)}; n=len(nodes)
    if duration/step*n**3>20000000 or duration/report*n>20000: raise ValueError('Air model exceeds numerical/output bounds; shorten event or partition network')
    compliance=[]; p=[]
    for node in nodes:
        fields(node,'id source_id air_volume_m3 initial_gauge_pa'); text(node,'source_id')
        compliance.append(num(node,'air_volume_m3',positive=True)/(exponent*atm)); p.append(num(node,'initial_gauge_pa'))
    if max(map(abs,p))>fraction*atm:raise ValueError('Initial air pressure exceeds the small-signal domain; use a validated compressible air model')
    vents=rows(data,'vents',empty=True,limit=50); unique(vents)
    for vent in vents:
        fields(vent,'id source_id from_node to_node linear_resistance_pa_s_m3 kind'); text(vent,'source_id')
        if vent.get('from_node') not in ids or vent.get('to_node') not in set(ids)|{'ATM'} or vent['from_node']==vent['to_node']:
            raise ValueError('Vent endpoints must name air nodes or ATM at the to_node')
        num(vent,'linear_resistance_pa_s_m3',positive=True)
        if vent.get('kind') not in ('open','AAV') or vent['kind']=='AAV' and vent['to_node']!='ATM':
            raise ValueError('Vent kind must be open or an AAV connected to atmosphere')
    displacements=rows(data,'displacements',empty=True,limit=50); unique(displacements)
    for d in displacements:
        fields(d,'id source_id node hydrograph'); text(d,'source_id')
        if d.get('node') not in ids: raise ValueError('Air displacement needs an existing node')
        points=rows(d,'hydrograph',limit=500)
        for row in points: fields(row,'time_s air_flow_lps'); num(row,'time_s',minimum=0,maximum=duration); num(row,'air_flow_lps')
        if points[0]['time_s']!=0 or points[-1]['time_s']!=duration or any(b['time_s']<=a['time_s'] for a,b in zip(points,points[1:])):
            raise ValueError('Air displacement must explicitly cover the event with increasing times')
    traps=rows(data,'traps',empty=True,limit=50); unique(traps); trapstate={}
    for trap in traps:
        fields(trap,'id source_id node seal_mm effective_liquid_length_m damping_pa_s_m density_kg_m3'); text(trap,'source_id')
        if trap.get('node') not in ids: raise ValueError('Trap needs an air node')
        num(trap,'seal_mm',positive=True); num(trap,'effective_liquid_length_m',positive=True)
        num(trap,'damping_pa_s_m',minimum=0); num(trap,'density_kg_m3',positive=True)
        trapstate[trap['id']]=[0.,0.]
    maximum=max(p); minimum=min(p); max_displacement=0.; t=0.; trace=[]; nextreport=0.; domain=False; broken=[]
    while t<duration-1e-10:
        dt=min(step,duration-t); rhs=[compliance[i]/dt*p[i] for i in range(n)]
        for d in displacements: rhs[ids[d['node']]]+=interpolate(d['hydrograph'],t+dt,'time_s','air_flow_lps')/1000
        guess=p[:]
        for iteration in range(25):
            mat=[[0.]*n for _ in range(n)]
            for i in range(n): mat[i][i]=compliance[i]/dt
            active=[]
            for v in vents:
                i=ids[v['from_node']]; j=ids.get(v['to_node']); delta=guess[i]-(guess[j] if j is not None else 0)
                isopen=v['kind']=='open' or delta<0; active.append(isopen)
                if not isopen: continue
                conductance=1/v['linear_resistance_pa_s_m3']; mat[i][i]+=conductance
                if j is not None: mat[i][j]-=conductance; mat[j][i]-=conductance; mat[j][j]+=conductance
            solved=_solve(mat,rhs)
            newactive=[v['kind']=='open' or solved[ids[v['from_node']]]<0 for v in vents]
            if all(v['kind']=='open' or a==b for v,a,b in zip(vents,active,newactive)): p=solved; break
            guess=solved
        else: raise ValueError('AAV active-set did not converge; reduce air-model timestep or review vent data')
        t+=dt; maximum=max(maximum,max(p)); minimum=min(minimum,min(p))
        if max(map(abs,p))>fraction*atm: domain=True
        for trap in traps:
            x,v=trapstate[trap['id']]; mass=trap['density_kg_m3']*trap['effective_liquid_length_m']
            damping=trap['damping_pa_s_m']/mass; spring=2*G/trap['effective_liquid_length_m']
            xn=((1+dt*damping)*x+dt*v+dt*dt*p[ids[trap['node']]]/mass)/(1+dt*damping+dt*dt*spring)
            trapstate[trap['id']]=[xn,(xn-x)/dt]; max_displacement=max(max_displacement,abs(xn)*1000)
            if abs(xn)*1000>=trap['seal_mm']: broken.append(trap['id'])
        if t+1e-9>=nextreport or domain or broken or t+1e-9>=duration:
            for identity,i in ids.items(): trace.append(dict(kind='air_node',id=identity,time_s=t,gauge_pa=p[i]))
            for trap in traps:
                x,v=trapstate[trap['id']]; trace.append(dict(kind='trap',id=trap['id'],time_s=t,one_leg_displacement_mm=x*1000,remaining_seal_mm=max(0,trap['seal_mm']-abs(x)*1000)))
            nextreport+=report
        if domain or broken: break
    return result(dict(maximum_gauge_pa=maximum,minimum_gauge_pa=minimum,maximum_trap_displacement_mm=max_displacement,
        simulated_duration_s=t,trap_seal_breach=bool(broken),small_pressure_domain_exceeded=domain),
        dict(maximum_gauge_pa='Pa gauge',minimum_gauge_pa='Pa gauge',maximum_trap_displacement_mm='mm',simulated_duration_s='s',trap_seal_breach='boolean',small_pressure_domain_exceeded='boolean'),
        [check('positive_air_pressure',maximum<=positive,maximum,positive,'Pa',ref),check('negative_air_pressure',minimum>=-negative,minimum,-negative,'Pa',ref),
         check('small_signal_domain',not domain,max(abs(maximum),abs(minimum))/atm,fraction,'1',ref),check('trap_seal_retained',not broken,broken,[],'trap IDs',ref)],trace,
        complete=not domain and not broken,
        notes=['Lumped polytropic air compliance with supplied linear vent resistances and one-way atmospheric AAV admission. Backward Euler/active-set integration; displacement hydrographs are independent inputs, not derived from DFU or SWMM liquid flow.',
            'Forced equal-leg U-trap oscillator with supplied damping, initially at rest; one-way pressure coupling neglects trap displacement feedback on air volume. Seal breach stops the simulation.',
            'Small-pressure, lumped-parameter method; does not resolve distributed acoustic waves, annular stack entrainment, solids, self-siphonage or every vent arrangement. Grid/time sensitivity and experimental validation remain required.'])
