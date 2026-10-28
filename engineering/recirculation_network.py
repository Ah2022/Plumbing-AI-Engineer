"""Conservative finite-volume no-draw recirculation with shared pipes/controls."""
import math
from engineering.common import fields, num, text, rows, unique, check, result, G


def recirculation_network(data):
    fields(data, 'source_id heater_node supply_temperature_c initial_temperature_c minimum_return_temperature_c '
        'minimum_distribution_temperature_c maximum_distribution_temperature_c water_density_kg_m3 specific_heat_j_kgk '
        'duration_s maximum_step_s report_step_s available_pump_head_m control pipes circuits')
    ref = text(data, 'source_id'); heater = text(data, 'heater_node')
    supply = num(data, 'supply_temperature_c', minimum=0, maximum=99)
    initial = num(data, 'initial_temperature_c', minimum=0, maximum=99)
    minimum = num(data, 'minimum_return_temperature_c', minimum=0, maximum=99)
    tmin = num(data, 'minimum_distribution_temperature_c', minimum=0, maximum=99)
    tmax = num(data, 'maximum_distribution_temperature_c', minimum=0, maximum=99)
    if tmin>tmax: raise ValueError('Distribution temperature limits are reversed')
    rho = num(data, 'water_density_kg_m3', positive=True); cp = num(data, 'specific_heat_j_kgk', positive=True)
    duration = num(data, 'duration_s', positive=True, maximum=86400)
    maxdt = num(data, 'maximum_step_s', positive=True, maximum=60)
    report = num(data, 'report_step_s', positive=True)
    if duration/report>2000: raise ValueError('At most 2000 report intervals')
    available = num(data, 'available_pump_head_m', minimum=0)
    pipes = rows(data, 'pipes', limit=100); unique(pipes)
    byid = {}; flows = {}; ins = {}; outs = {}; volumes = {}; heat = {}; temperatures = {}
    for p in pipes:
        fields(p, 'id source_id from_node to_node length_m internal_mm ua_w_k ambient_temperature_c friction_factor fittings_k cells')
        identity = text(p, 'id'); text(p, 'source_id'); a=text(p,'from_node'); b=text(p,'to_node')
        if a==b: raise ValueError('A recirculation pipe must connect different nodes')
        length = num(p, 'length_m', positive=True); d = num(p, 'internal_mm', positive=True)/1000
        nc = num(p, 'cells', minimum=1, maximum=100)
        if int(nc)!=nc: raise ValueError('Pipe cell count must be an integer')
        num(p,'friction_factor',positive=True,maximum=1); num(p,'fittings_k',minimum=0)
        num(p,'ambient_temperature_c',minimum=0,maximum=99)
        heat[identity]=num(p,'ua_w_k',minimum=0)
        volumes[identity]=length*math.pi*d*d/4
        byid[identity]=p; flows[identity]=0.; temperatures[identity]=[initial]*int(nc)
        ins.setdefault(b,[]).append(identity); outs.setdefault(a,[]).append(identity)
    circuits = rows(data,'circuits',limit=100); unique(circuits)
    paths = {}
    for c in circuits:
        fields(c,'id source_id selected_flow_lps pipe_ids'); text(c,'source_id')
        path=c.get('pipe_ids')
        if not isinstance(path,list) or not path or len(path)>len(pipes) or len(set(path))!=len(path):
            raise ValueError('Each circuit needs an ordered, nonrepeating closed pipe path')
        node=heater; q=num(c,'selected_flow_lps',positive=True)/1000
        for identity in path:
            if identity not in byid or byid[identity]['from_node']!=node:
                raise ValueError('Circuit pipes must form a directed closed path beginning at the heater')
            flows[identity]+=q; node=byid[identity]['to_node']
        if node!=heater: raise ValueError('Every circuit must return to the heater')
        paths[c['id']]=path
    if any(q<=0 for q in flows.values()): raise ValueError('Every modeled pipe must belong to a circulation circuit')
    nodes=set(ins)|set(outs)
    for n in nodes:
        if abs(sum(flows[p] for p in ins.get(n,[]))-sum(flows[p] for p in outs.get(n,[])))>1e-10:
            raise ValueError('Recirculation node continuity is not satisfied at '+n)
    total=sum(flows[p] for p in outs[heater]); head={}
    for identity,p in byid.items():
        d=p['internal_mm']/1000; v=flows[identity]/(math.pi*d*d/4)
        head[identity]=(p['friction_factor']*p['length_m']/d+p['fittings_k'])*v*v/(2*G)
    loopheads={c:sum(head[p] for p in path) for c,path in paths.items()}; governing=max(loopheads.values())
    control=data.get('control'); fields(control,'mode sensor_node on_below_c off_above_c schedule')
    mode=control.get('mode')
    if mode not in ('continuous','thermostat','schedule'): raise ValueError('Control mode must be continuous, thermostat or schedule')
    if mode=='thermostat':
        sensor=text(control,'sensor_node')
        if sensor not in ins: raise ValueError('Thermostat sensor needs an incoming pipe at its node')
        on=num(control,'on_below_c',minimum=0,maximum=99); off=num(control,'off_above_c',minimum=0,maximum=99)
        if on>=off: raise ValueError('Thermostat requires on_below_c < off_above_c')
    schedule=[]
    if mode=='schedule':
        from engineering.common import flag
        schedule=rows(control,'schedule',limit=200)
        for row in schedule:
            fields(row,'time_s enabled'); num(row,'time_s',minimum=0,maximum=duration); flag(row,'enabled')
        if schedule[0]['time_s']!=0 or any(b['time_s']<=a['time_s'] for a,b in zip(schedule,schedule[1:])):
            raise ValueError('Schedule must start at zero and increase strictly')
    # Explicit upwind CFL plus loss coefficient preserves positivity/conservation.
    stable=min(.8/(flows[p]*len(temperatures[p])/volumes[p]+heat[p]/(rho*cp*volumes[p])) for p in byid)
    dtbase=min(maxdt,stable)
    cells=sum(map(len,temperatures.values()))
    if math.ceil(duration/dtbase)*cells>5000000:
        raise ValueError('Thermal network exceeds five million cell updates; reduce duration/cells or partition it')
    def node_t(n):
        return sum(flows[p]*temperatures[p][-1] for p in ins[n])/sum(flows[p] for p in ins[n])
    start_energy=sum(rho*cp*volumes[p]*initial for p in byid)
    t=0.; nextreport=0.; enabled=True; heater_energy=0.; loss_energy=0.; ontime=0.; exposure=0.
    mint=initial; maxt=max(initial,supply); minreturn=initial; switches=0; trace=[]
    while t<duration-1e-10:
        was=enabled
        if mode=='thermostat':
            sensor_t=node_t(control['sensor_node'])
            if sensor_t<=on: enabled=True
            elif sensor_t>=off: enabled=False
        elif mode=='schedule': enabled=next(row['enabled'] for row in reversed(schedule) if row['time_s']<=t+1e-10)
        switches+=int(was!=enabled)
        dt=min(dtbase,duration-t)
        if schedule:
            future=[row['time_s']-t for row in schedule if row['time_s']>t+1e-10]
            if future: dt=min(dt,min(future))
        returning=node_t(heater)
        if enabled: minreturn=min(minreturn,returning); ontime+=dt
        if any(min(v)<tmin for v in temperatures.values()): exposure+=dt
        if t+1e-9>=nextreport:
            trace.append(dict(kind='time',time_s=t,pump_on=enabled,return_temperature_c=returning,
                minimum_water_temperature_c=min(map(min,temperatures.values())),maximum_water_temperature_c=max(map(max,temperatures.values()))))
            nextreport+=report
        inlet={n:(supply if n==heater else node_t(n)) for n in nodes}
        new={}; step_loss=0.
        for identity,p in byid.items():
            old=temperatures[identity]; nc=len(old); cellvol=volumes[identity]/nc
            q=flows[identity] if enabled else 0.; ua=heat[identity]/nc
            new[identity]=[]
            for j,value in enumerate(old):
                upstream=old[j-1] if j else inlet[p['from_node']]
                loss=ua*(value-p['ambient_temperature_c']); step_loss+=loss
                new[identity].append(value+dt*(q/cellvol*(upstream-value)-loss/(rho*cp*cellvol)))
        heater_energy+=(rho*cp*total*(supply-returning) if enabled else 0)*dt
        loss_energy+=step_loss*dt; temperatures=new; t+=dt
        mint=min(mint,min(map(min,temperatures.values()))); maxt=max(maxt,max(map(max,temperatures.values())))
    returning=node_t(heater)
    if enabled: minreturn=min(minreturn,returning)
    trace.append(dict(kind='time',time_s=duration,pump_on=enabled,return_temperature_c=returning,
        minimum_water_temperature_c=min(map(min,temperatures.values())),maximum_water_temperature_c=max(map(max,temperatures.values()))))
    for identity in byid:
        trace.append(dict(kind='pipe',id=identity,selected_flow_lps=flows[identity]*1000,head_loss_m=head[identity],
            final_outlet_temperature_c=temperatures[identity][-1],source_id=byid[identity]['source_id']))
    for c in circuits:
        trace.append(dict(kind='circuit',id=c['id'],circuit_head_m=loopheads[c['id']],
            additional_balancing_head_m=governing-loopheads[c['id']],source_id=c['source_id']))
    final_energy=sum(rho*cp*volumes[p]*sum(temperatures[p])/len(temperatures[p]) for p in byid)
    residual=final_energy-start_energy-heater_energy+loss_energy
    checks=[check('circulation_pump_head',available>=governing,available,governing,'m',ref),
        check('return_temperature_while_running',ontime>0 and minreturn>=minimum,minreturn,minimum,'C',ref),
        check('distribution_low_temperature',mint>=tmin,mint,tmin,'C',ref),
        check('distribution_high_temperature',maxt<=tmax,maxt,tmax,'C',ref),
        check('energy_conservation',abs(residual)<=max(1,abs(heater_energy))*1e-8,residual,0,'J',ref)]
    return result(dict(total_circulation_flow_lps=total*1000,governing_loop_head_m=governing,
        final_return_temperature_c=returning,minimum_water_temperature_c=mint,maximum_water_temperature_c=maxt,
        pump_on_time_s=ontime,control_switches=switches,low_temperature_exposure_s=exposure,
        heater_energy_kwh=heater_energy/3600000,ambient_heat_loss_kwh=loss_energy/3600000,energy_residual_j=residual),
        dict(total_circulation_flow_lps='L/s',governing_loop_head_m='m',final_return_temperature_c='C',minimum_water_temperature_c='C',
            maximum_water_temperature_c='C',pump_on_time_s='s',control_switches='count',low_temperature_exposure_s='s',
            heater_energy_kwh='kWh',ambient_heat_loss_kwh='kWh',energy_residual_j='J'),checks,trace,
        notes=['Directed closed circuits prescribe balanced flows. Shared pipes accumulate circuit flows; shared heat loss and water inventory are counted once. Supply heater is an ideal fixed-temperature boundary.',
            'Finite-volume upwind advection with mixed zero-volume junctions, ambient UA loss and automatically bounded timestep; check mesh/time sensitivity for design use.',
            'No fixture draws, stratified storage, variable hydraulic balancing, check-valve dynamics or microbiological prediction. Temperature/exposure flags do not establish hygiene or scald-safety approval.'])
