"""Experimental conservative chamber/filled-link liquid-air-solids coupling.

This is a reduced-order two-phase model, not a vertical-stack annular CFD solver.
Air pressure feeds liquid momentum; liquid/trap displacement changes air volume.
All transported and deposited solids are accounted for as dilute tracer mass.
"""
import math
import numpy as np
from engineering.common import fields,num,text,rows,unique,check,result,G,interpolate


def coupled_drainage(data):
    fields(data,'source_id density_kg_m3 air_constant_j_kgk atmospheric_kpa duration_s maximum_step_s '
        'report_step_s maximum_air_gauge_pa maximum_concentration_kg_m3 nodes pipes vents inflows traps')
    ref=text(data,'source_id'); rho=num(data,'density_kg_m3',positive=True)
    gasr=num(data,'air_constant_j_kgk',positive=True); atm=num(data,'atmospheric_kpa',positive=True)*1000
    duration=num(data,'duration_s',positive=True,maximum=600); maxdt=num(data,'maximum_step_s',positive=True,maximum=.1)
    report=num(data,'report_step_s',positive=True); limit=num(data,'maximum_air_gauge_pa',positive=True,maximum=.1*atm)
    clim=num(data,'maximum_concentration_kg_m3',positive=True,maximum=.01*rho)
    nodes=rows(data,'nodes',limit=20); pipes=rows(data,'pipes',empty=True,limit=30)
    vents=rows(data,'vents',empty=True,limit=30); inflows=rows(data,'inflows',empty=True,limit=30); traps=rows(data,'traps',empty=True,limit=20)
    for values in (nodes,pipes,vents,inflows,traps):unique(values)
    if (len(nodes)+len(pipes)+len(traps))*duration/report>30000:raise ValueError('Too many report samples; increase report interval')
    ids={text(n,'id'):i for i,n in enumerate(nodes)}; n=len(nodes); e=len(pipes); nt=len(traps)
    # V, air mass, suspended mass, bed mass, pipe Q, trap x and velocity;
    # last four values integrate external water/air/solid mass and vent air mass.
    state=np.zeros(4*n+e+2*nt+4); boundary=[]; temperatures=[]
    for i,node in enumerate(nodes):
        fields(node,'id source_id kind invert_m area_m2 total_volume_m3 initial_liquid_m3 initial_air_absolute_kpa '
            'air_temperature_k initial_concentration_kg_m3 initial_bed_kg settling_rate_per_s resuspension_rate_per_s resuspension_velocity_m_s')
        text(node,'source_id');num(node,'invert_m');num(node,'area_m2',positive=True)
        total=num(node,'total_volume_m3',positive=True); water=num(node,'initial_liquid_m3',positive=True,maximum=total)
        if water>=total:raise ValueError('A coupled chamber needs a positive initial air pocket')
        if node.get('kind') not in ('chamber','reservoir'):raise ValueError('Node kind must be chamber or reservoir')
        boundary.append(node['kind']=='reservoir');temp=num(node,'air_temperature_k',positive=True);temperatures.append(temp)
        pressure=num(node,'initial_air_absolute_kpa',positive=True)*1000
        state[i]=water;state[n+i]=pressure*(total-water)/(gasr*temp)
        state[2*n+i]=water*num(node,'initial_concentration_kg_m3',minimum=0,maximum=clim)
        state[3*n+i]=num(node,'initial_bed_kg',minimum=0)
        for key in ('settling_rate_per_s','resuspension_rate_per_s','resuspension_velocity_m_s'):num(node,key,minimum=0)
    if all(boundary):raise ValueError('At least one dynamic chamber is required')
    for p in pipes:
        fields(p,'id source_id from_node to_node length_m internal_mm friction_factor fittings_k port_from_m port_to_m initial_flow_lps')
        text(p,'source_id');a=text(p,'from_node');b=text(p,'to_node')
        if a not in ids or b not in ids or a==b:raise ValueError('Invalid liquid-link endpoints')
        num(p,'length_m',positive=True);num(p,'internal_mm',positive=True)
        num(p,'friction_factor',minimum=0,maximum=1);num(p,'fittings_k',minimum=0)
        num(p,'port_from_m',minimum=0);num(p,'port_to_m',minimum=0);num(p,'initial_flow_lps')
    for j,p in enumerate(pipes):state[4*n+j]=p['initial_flow_lps']/1000
    for v in vents:
        fields(v,'id source_id from_node to_node kind resistance_pa_s_m3')
        text(v,'source_id');a=text(v,'from_node');b=text(v,'to_node')
        if a not in ids or b not in set(ids)|{'ATM'} or a==b:raise ValueError('Invalid vent endpoints')
        if v.get('kind') not in ('open','AAV') or v['kind']=='AAV' and b!='ATM':raise ValueError('AAV can admit atmosphere only')
        num(v,'resistance_pa_s_m3',positive=True)
    for f in inflows:
        fields(f,'id source_id node concentration_kg_m3 hydrograph');text(f,'source_id')
        if f.get('node') not in ids or boundary[ids[f['node']]]:raise ValueError('Inflows require a dynamic chamber')
        num(f,'concentration_kg_m3',minimum=0,maximum=clim);points=rows(f,'hydrograph',limit=500)
        for point in points:fields(point,'time_s flow_lps');num(point,'time_s',minimum=0,maximum=duration);num(point,'flow_lps',minimum=0)
        if points[0]['time_s']!=0 or points[-1]['time_s']!=duration or any(b['time_s']<=a['time_s'] for a,b in zip(points,points[1:])):raise ValueError('Inflow must cover the event with increasing times')
    for trap in traps:
        fields(trap,'id source_id node leg_area_m2 effective_length_m seal_mm damping_pa_s_m');text(trap,'source_id')
        if trap.get('node') not in ids or boundary[ids[trap['node']]]:raise ValueError('Traps require dynamic chambers')
        for key in ('leg_area_m2','effective_length_m','seal_mm'):num(trap,key,positive=True)
        num(trap,'damping_pa_s_m',minimum=0)
    def quantities(y):
        va=np.array([node['total_volume_m3'] for node in nodes])-y[:n]
        for j,tr in enumerate(traps):va[ids[tr['node']]]+=tr['leg_area_m2']*y[4*n+e+j]
        if min(y[:n])<=0 or min(va)<=0 or min(y[n:2*n])<=0 or min(y[2*n:4*n])<-1e-12:
            raise ValueError('Chamber/air/solids positivity exceeded; dewatering or pocket collapse needs another model')
        pressure=y[n:2*n]*gasr*np.array(temperatures)/va
        return va,pressure,y[2*n:3*n]/y[:n]
    def derivative(y,time):
        va,p,c=quantities(y);dy=np.zeros_like(y);velocities=[0.]*n
        for j,pipe in enumerate(pipes):
            a=ids[pipe['from_node']];b=ids[pipe['to_node']];d=pipe['internal_mm']/1000;area=math.pi*d*d/4;q=y[4*n+j]
            if y[a]/nodes[a]['area_m2']<pipe['port_from_m']+d or y[b]/nodes[b]['area_m2']<pipe['port_to_m']+d:
                raise ValueError('A liquid link is not fully submerged; free-surface/annular transitions are not implemented')
            head=[nodes[k]['invert_m']+y[k]/nodes[k]['area_m2']+(p[k]-atm)/(rho*G) for k in (a,b)]
            dy[4*n+j]=G*area/pipe['length_m']*(head[0]-head[1])-(pipe['friction_factor']*pipe['length_m']/d+pipe['fittings_k'])*q*abs(q)/(2*pipe['length_m']*area)
            donor=a if q>=0 else b;mass=q*c[donor]
            for k,sign in ((a,-1),(b,1)):
                velocities[k]=max(velocities[k],abs(q)/area)
                if not boundary[k]:dy[k]+=sign*q;dy[2*n+k]+=sign*mass
                else:dy[-4]-=sign*q;dy[-2]-=sign*mass
        for vent in vents:
            a=ids[vent['from_node']];b=ids.get(vent['to_node']);pb=p[b] if b is not None else atm
            q=(p[a]-pb)/vent['resistance_pa_s_m3']
            if vent['kind']=='AAV':q=min(0,q)
            density=(p[a]/(gasr*temperatures[a]) if q>=0 else pb/(gasr*(temperatures[b] if b is not None else temperatures[a])))
            mass=q*density
            if not boundary[a]:dy[n+a]-=mass
            else:dy[-1]-=mass
            if b is not None and not boundary[b]:dy[n+b]+=mass
            else:dy[-1]+=mass
        for flow in inflows:
            k=ids[flow['node']];q=interpolate(flow['hydrograph'],time,'time_s','flow_lps')/1000
            dy[k]+=q;dy[2*n+k]+=q*flow['concentration_kg_m3'];dy[-4]+=q;dy[-2]+=q*flow['concentration_kg_m3']
        for k,node in enumerate(nodes):
            if boundary[k]:continue
            settled=node['settling_rate_per_s']*y[2*n+k]
            entrained=node['resuspension_rate_per_s']*y[3*n+k] if velocities[k]>=node['resuspension_velocity_m_s'] else 0
            dy[2*n+k]+=entrained-settled;dy[3*n+k]+=settled-entrained
        for j,trap in enumerate(traps):
            xindex=4*n+e+j;vindex=xindex+nt;k=ids[trap['node']]
            dy[xindex]=y[vindex]
            dy[vindex]=(p[k]-atm-2*rho*G*y[xindex]-trap['damping_pa_s_m']*y[vindex])/(rho*trap['effective_length_m'])
        return dy
    dynamic=[i for i in range(n) if not boundary[i]]
    initial_water=sum(state[k] for k in dynamic);initial_air=sum(state[n+k] for k in dynamic)
    initial_solids=sum(state[2*n+k]+state[3*n+k] for k in dynamic)
    t=0.;nextreport=0.;trace=[];peak=0.;peakc=0.;stopped='';steps=0
    while True:
        va,pressure,concentration=quantities(state);peak=max(peak,max(abs(pressure[k]-atm) for k in dynamic));peakc=max(peakc,max(concentration[k] for k in dynamic))
        if peak>limit:stopped='Air-pressure validity/criterion limit exceeded'
        if peakc>clim:stopped='Dilute solids concentration limit exceeded'
        if any(abs(state[4*n+e+j])*1000>=tr['seal_mm'] for j,tr in enumerate(traps)):stopped='Trap seal breach'
        if t+1e-10>=nextreport or stopped or t+1e-10>=duration:
            for identity,k in ids.items():trace.append(dict(kind='chamber',id=identity,time_s=t,liquid_m3=state[k],air_absolute_kpa=pressure[k]/1000,
                air_gauge_pa=pressure[k]-atm,air_mass_kg=state[n+k],suspended_kg=state[2*n+k],deposited_kg=state[3*n+k]))
            for j,p in enumerate(pipes):trace.append(dict(kind='pipe',id=p['id'],time_s=t,flow_lps=state[4*n+j]*1000))
            nextreport+=report
        if stopped or t+1e-10>=duration:break
        dt=min(maxdt,duration-t)
        for v in vents:
            k=ids[v['from_node']];dt=min(dt,.1*v['resistance_pa_s_m3']*va[k]/pressure[k])
            if v['to_node'] in ids:
                k=ids[v['to_node']];dt=min(dt,.1*v['resistance_pa_s_m3']*va[k]/pressure[k])
        first=derivative(state,t)
        for retry in range(20):
            try:
                predicted=state+dt*first;second=derivative(predicted,t+dt);candidate=state+dt/2*(first+second);quantities(candidate);break
            except ValueError:
                dt/=2
        else:stopped='Positivity/submergence boundary reached; refine model or use a phase-transition solver';continue
        if dt<1e-8 or steps>=200000:stopped='Numerical step limit exceeded; reduce event/geometry stiffness';continue
        state=candidate;t+=dt;steps+=1
    water_error=sum(state[k] for k in dynamic)-initial_water-state[-4]
    air_error=sum(state[n+k] for k in dynamic)-initial_air+state[-1]
    solid_error=sum(state[2*n+k]+state[3*n+k] for k in dynamic)-initial_solids-state[-2]
    values=dict(simulated_duration_s=t,maximum_air_gauge_magnitude_pa=peak,maximum_suspended_kg_m3=peakc,
        liquid_balance_error_m3=water_error,air_balance_error_kg=air_error,solids_balance_error_kg=solid_error,
        final_liquid_m3=sum(state[k] for k in dynamic),final_air_mass_kg=sum(state[n+k] for k in dynamic),
        final_suspended_kg=sum(state[2*n+k] for k in dynamic),final_deposited_kg=sum(state[3*n+k] for k in dynamic),stop_reason=stopped or 'EVENT_COMPLETED')
    return result(values,dict(simulated_duration_s='s',maximum_air_gauge_magnitude_pa='Pa',maximum_suspended_kg_m3='kg/m³',liquid_balance_error_m3='m³',
        air_balance_error_kg='kg',solids_balance_error_kg='kg',final_liquid_m3='m³',final_air_mass_kg='kg',final_suspended_kg='kg',final_deposited_kg='kg',stop_reason='status'),
        [check('coupled_domain',not stopped,stopped or 'within supplied domain','within supplied domain','status',ref),
         check('liquid_conservation',abs(water_error)<1e-8,water_error,0,'m³',ref),check('air_conservation',abs(air_error)<1e-8,air_error,0,'kg',ref),
         check('solids_conservation',abs(solid_error)<1e-8,solid_error,0,'kg',ref)],trace,complete=not stopped,
        notes=['EXPERIMENTAL reduced-order two-phase chamber model: incompressible liquid storage/inertial filled links, isothermal compressible air, open vents/AAVs and optional equal-leg trap displacement feedback. Conservative Heun integration.',
            'Dilute well-mixed suspended tracer and empirical deposition/resuspension rates; reservoir exchanges and vent air are included in mass balances. Pipe transit time, settling beds within pipes, blockages, rags and discrete-solid transport are not modeled.',
            'All liquid links must remain flooded/submerged. No free-surface-to-annular/slug transition, vertical-stack entrainment closure, distributed air waves or complete code vent behavior. Requires laboratory comparison and timestep convergence before design acceptance.'])
