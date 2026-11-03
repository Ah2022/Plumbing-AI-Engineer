"""Conservative stratified storage, hot-line draws, TMV response and exposure flags."""
import math
from engineering.common import fields,num,text,rows,unique,flag,check,result


def _restratify(temperatures,ages,volumes):
    blocks=[]
    for i,(temp,age,vol) in enumerate(zip(temperatures,ages,volumes)):
        blocks.append([i,i,vol,vol*temp,vol*age])
        while len(blocks)>1 and blocks[-2][3]/blocks[-2][2]>blocks[-1][3]/blocks[-1][2]:
            b=blocks.pop();a=blocks.pop();blocks.append([a[0],b[1],a[2]+b[2],a[3]+b[3],a[4]+b[4]])
    for lo,hi,vol,heat,age in blocks:
        for i in range(lo,hi+1):temperatures[i]=heat/vol;ages[i]=age/vol


def hot_water_draw(data):
    fields(data,'source_id duration_s maximum_step_s report_step_s density_kg_m3 specific_heat_j_kgk cold_temperature_c '
        'tank_ambient_c layer_conductance_w_k heater_on_below_c heater_off_above_c heater_sensor_layer '
        'minimum_storage_c hygiene_band_low_c hygiene_band_high_c disinfection_temperature_c required_dwell_s '
        'maximum_water_age_s minimum_delivered_fraction layers fixtures events')
    ref=text(data,'source_id');duration=num(data,'duration_s',positive=True,maximum=86400)
    maxdt=num(data,'maximum_step_s',positive=True,maximum=10);report=num(data,'report_step_s',positive=True)
    rho=num(data,'density_kg_m3',positive=True);cp=num(data,'specific_heat_j_kgk',positive=True)
    cold=num(data,'cold_temperature_c',minimum=0,maximum=99);ambient=num(data,'tank_ambient_c',minimum=0,maximum=99)
    conductance=num(data,'layer_conductance_w_k',minimum=0)
    on=num(data,'heater_on_below_c',minimum=0,maximum=99);off=num(data,'heater_off_above_c',minimum=0,maximum=99)
    if on>=off:raise ValueError('Heater thresholds require on < off')
    minimum=num(data,'minimum_storage_c',minimum=0,maximum=99)
    low=num(data,'hygiene_band_low_c',minimum=0,maximum=99);high=num(data,'hygiene_band_high_c',minimum=0,maximum=99)
    if low>=high:raise ValueError('Hygiene exposure band requires low < high')
    disinfect=num(data,'disinfection_temperature_c',minimum=0,maximum=99);dwell=num(data,'required_dwell_s',minimum=0)
    age_limit=num(data,'maximum_water_age_s',positive=True)
    required_fraction=num(data,'minimum_delivered_fraction',minimum=0,maximum=1)
    layers=rows(data,'layers',limit=30);unique(layers);vol=[];temp=[];ages=[]
    for layer in layers:
        fields(layer,'id source_id volume_l initial_temperature_c initial_age_s heater_power_w ua_w_k');text(layer,'source_id')
        vol.append(num(layer,'volume_l',positive=True)/1000);temp.append(num(layer,'initial_temperature_c',minimum=0,maximum=99));ages.append(num(layer,'initial_age_s',minimum=0))
        num(layer,'heater_power_w',minimum=0);num(layer,'ua_w_k',minimum=0)
    sensor=num(data,'heater_sensor_layer',minimum=0,maximum=len(layers)-1)
    if int(sensor)!=sensor:raise ValueError('Heater sensor layer is a zero-based integer, bottom to top')
    sensor=int(sensor);fixtures=rows(data,'fixtures',limit=30);unique(fixtures);byid={f['id']:f for f in fixtures};lines={};lineages={};fractions={};failure={}
    for f in fixtures:
        fields(f,'id source_id hot_line_volume_l cells initial_temperature_c initial_age_s ua_w_k ambient_c '
            'target_temperature_c scald_limit_c minimum_delivery_c response_time_s initial_hot_fraction cold_failure_close_s')
        text(f,'source_id');num(f,'hot_line_volume_l',positive=True)
        nc=num(f,'cells',minimum=1,maximum=100)
        if int(nc)!=nc:raise ValueError('Hot-line cell count must be integer')
        for key in ('initial_temperature_c','ambient_c','target_temperature_c','scald_limit_c','minimum_delivery_c'):num(f,key,minimum=0,maximum=99)
        if f['target_temperature_c']<cold:raise ValueError('Target mixed temperature cannot be below cold supply')
        for key in ('ua_w_k','initial_age_s','response_time_s','cold_failure_close_s'):num(f,key,minimum=0)
        fractions[f['id']]=num(f,'initial_hot_fraction',minimum=0,maximum=1);failure[f['id']]=0.
        lines[f['id']]=[f['initial_temperature_c']]*int(nc);lineages[f['id']]=[f['initial_age_s']]*int(nc)
    events=rows(data,'events',empty=True,limit=500)
    for event in events:
        fields(event,'fixture source_id start_s end_s mixed_flow_lps cold_available');text(event,'source_id')
        if event.get('fixture') not in byid:raise ValueError('Draw event references unknown fixture')
        start=num(event,'start_s',minimum=0,maximum=duration);end=num(event,'end_s',minimum=0,maximum=duration)
        if end<=start:raise ValueError('Draw event must have end > start')
        num(event,'mixed_flow_lps',positive=True);flag(event,'cold_available')
    for identity in byid:
        ordered=sorted([e for e in events if e['fixture']==identity],key=lambda e:e['start_s'])
        if any(b['start_s']<a['end_s'] for a,b in zip(ordered,ordered[1:])):raise ValueError('Draw events for the same fixture cannot overlap')
    count=sum(map(len,lines.values()))+len(layers)
    if duration/maxdt*count>5000000 or duration/report*(len(fixtures)+len(layers))>30000:raise ValueError('Thermal event exceeds computation/report bounds')
    def energy():return rho*cp*(sum(v*t for v,t in zip(vol,temp))+sum(byid[i]['hot_line_volume_l']/1000*sum(v)/len(v) for i,v in lines.items()))
    initial_energy=energy();heater=True;heater_j=0.;ambient_j=0.;makeup_j=0.;out_j=0.;hot_volume=0.;mixed_volume=0.
    minstorage=min(temp);maxage=max(ages+[a for v in lineages.values() for a in v]);scald_s=0.;under_s=0.;band_m3s=0.;peakout=None;requested_volume=0.
    continuous=[0.]*len(layers);maxdwell=[0.]*len(layers);trace=[];t=0.;nextreport=0.;steps=0;stop=''
    while t<duration-1e-10:
        if temp[sensor]<=on:heater=True
        elif temp[sensor]>=off:heater=False
        active={f:next((e for e in events if e['fixture']==f and e['start_s']<=t+1e-10<e['end_s']),None) for f in byid}
        dt=min(maxdt,duration-t)
        future=[point-t for e in events for point in (e['start_s'],e['end_s']) if point>t+1e-9]
        if future:dt=min(dt,min(future))
        flow={};mixed={};outlets={};newfraction={}
        for identity,f in byid.items():
            event=active[identity]
            if not event:flow[identity]=mixed[identity]=0.;outlets[identity]=None;newfraction[identity]=fractions[identity];continue
            hot=lines[identity][-1];desired=min(1,max(0,(f['target_temperature_c']-cold)/(hot-cold))) if hot>cold else 1.
            if not event['cold_available'] and failure[identity]>=f['cold_failure_close_s']-1e-9:
                fraction=0.;flow[identity]=mixed[identity]=0.;outlets[identity]=None
            else:
                fraction=desired if f['response_time_s']==0 else desired+(fractions[identity]-desired)*math.exp(-dt/f['response_time_s'])
                q=event['mixed_flow_lps']/1000;flow[identity]=q*(fraction+fractions[identity])/2 if f['response_time_s'] else q*fraction
                mixed[identity]=q if event['cold_available'] else flow[identity]
                outlets[identity]=(hot*flow[identity]+cold*(q-flow[identity]))/q if event['cold_available'] else hot
                if not event['cold_available']:
                    dt=min(dt,max(1e-9,f['cold_failure_close_s']-failure[identity]))
            newfraction[identity]=fraction
            # Requested flow is a conservative bound for a changing actuator.
            dt=min(dt,.8*(f['hot_line_volume_l']/1000/len(lines[identity]))/(event['mixed_flow_lps']/1000))
            if f['ua_w_k']>0:dt=min(dt,.8*rho*cp*f['hot_line_volume_l']/1000/f['ua_w_k'])
        totalq=sum(e['mixed_flow_lps']/1000 for e in active.values() if e is not None)
        for i,layer in enumerate(layers):
            rate=totalq/vol[i]+(layer['ua_w_k']+2*conductance)/(rho*cp*vol[i])
            if rate>0:dt=min(dt,.8/rate)
        if dt<1e-8 or steps>=200000:stop='Thermal timestep limit exceeded';break
        # Fraction evolution above assumes a fixed inlet for the tentative step.
        # Recompute at the actual bounded dt so actuator dynamics do not accelerate.
        for identity,f in byid.items():
            event=active[identity]
            if not event:continue
            hot=lines[identity][-1];desired=min(1,max(0,(f['target_temperature_c']-cold)/(hot-cold))) if hot>cold else 1.
            if event['cold_available'] or failure[identity]<f['cold_failure_close_s']-1e-9:
                fraction=desired if not f['response_time_s'] else desired+(fractions[identity]-desired)*math.exp(-dt/f['response_time_s'])
                average=desired if not f['response_time_s'] else desired+(fractions[identity]-desired)*f['response_time_s']*(-math.expm1(-dt/f['response_time_s']))/dt
                q=event['mixed_flow_lps']/1000;flow[identity]=q*average;mixed[identity]=q if event['cold_available'] else flow[identity]
                outlets[identity]=(hot*flow[identity]+cold*(q-flow[identity]))/q if event['cold_available'] else hot;newfraction[identity]=fraction
        totalq=sum(flow.values());old=temp[:];oldages=ages[:];loss=sum(l['ua_w_k']*(old[i]-ambient) for i,l in enumerate(layers));power=sum(l['heater_power_w'] for l in layers) if heater else 0.
        for i,layer in enumerate(layers):
            upstream=cold if i==0 else old[i-1];upage=0 if i==0 else oldages[i-1]
            exchange=conductance*((old[i-1]-old[i] if i else 0)+(old[i+1]-old[i] if i+1<len(layers) else 0))
            heating=layer['heater_power_w'] if heater else 0
            temp[i]+=dt*(totalq/vol[i]*(upstream-old[i])+(heating-layer['ua_w_k']*(old[i]-ambient)+exchange)/(rho*cp*vol[i]))
            ages[i]+=dt*(1+totalq/vol[i]*(upage-oldages[i]))
        _restratify(temp,ages,vol)
        for identity,f in byid.items():
            values=lines[identity];agevalues=lineages[identity];v=f['hot_line_volume_l']/1000/len(values);q=flow[identity]
            before=values[:];beforeage=agevalues[:]
            for i,value in enumerate(before):
                heatloss=f['ua_w_k']/len(values)*(value-f['ambient_c']);loss+=heatloss
                values[i]+=dt*(q/v*((before[i-1] if i else old[-1])-value)-heatloss/(rho*cp*v))
                agevalues[i]+=dt*(1+q/v*((beforeage[i-1] if i else oldages[-1])-beforeage[i]))
            out_j+=rho*cp*q*before[-1]*dt
            hot_volume+=q*dt;mixed_volume+=mixed[identity]*dt
            if outlets[identity] is not None and mixed[identity]>0:
                peakout=max(peakout if peakout is not None else outlets[identity],outlets[identity]);scald_s+=dt if outlets[identity]>f['scald_limit_c'] else 0
                under_s+=dt if outlets[identity]<f['minimum_delivery_c'] else 0
            event=active[identity];failure[identity]=failure[identity]+dt if event and not event['cold_available'] else 0.
        requested_volume+=sum(e['mixed_flow_lps']/1000 for e in active.values() if e is not None)*dt
        heater_j+=power*dt;ambient_j+=loss*dt;makeup_j+=rho*cp*totalq*cold*dt;fractions=newfraction;t+=dt;steps+=1
        minstorage=min(minstorage,min(temp));maxage=max(maxage,max(ages+[a for v in lineages.values() for a in v]))
        band_m3s+=dt*(sum(v for v,tt in zip(vol,temp) if low<=tt<=high)+sum(f['hot_line_volume_l']/1000*sum(low<=tt<=high for tt in lines[identity])/len(lines[identity]) for identity,f in byid.items()))
        for i,tt in enumerate(temp):continuous[i]=continuous[i]+dt if tt>=disinfect else 0.;maxdwell[i]=max(maxdwell[i],continuous[i])
        if any(not 0<=tt<=99 for tt in temp+[tt for values in lines.values() for tt in values]):stop='Single-phase water temperature domain exceeded'
        if t+1e-9>=nextreport or t+1e-9>=duration or stop:
            for i,layer in enumerate(layers):trace.append(dict(kind='layer',id=layer['id'],time_s=t,temperature_c=temp[i],mean_water_age_s=ages[i]))
            for identity in byid:trace.append(dict(kind='fixture',id=identity,time_s=t,hot_inlet_temperature_c=lines[identity][-1],delivered_temperature_c=outlets[identity],mixed_flow_lps=mixed[identity]*1000,hot_fraction=fractions[identity]))
            nextreport+=report
        if stop:break
    residual=energy()-initial_energy-heater_j+ambient_j-makeup_j+out_j
    values=dict(final_tank_top_c=temp[-1],final_tank_bottom_c=temp[0],minimum_storage_c=minstorage,maximum_outlet_c=peakout,
        hot_draw_l=hot_volume*1000,mixed_delivery_l=mixed_volume*1000,scald_exposure_fixture_s=scald_s,under_temperature_fixture_s=under_s,
        hygiene_band_volume_time_l_s=band_m3s*1000,maximum_modeled_water_age_s=maxage,minimum_layer_maximum_hot_dwell_s=min(maxdwell),
        requested_draw_l=requested_volume*1000,unmet_draw_l=max(0,requested_volume-mixed_volume)*1000,
        energy_balance_residual_j=residual,simulated_duration_s=t,stop_reason=stop or 'EVENT_COMPLETED')
    return result(values,dict(final_tank_top_c='C',final_tank_bottom_c='C',minimum_storage_c='C',maximum_outlet_c='C',hot_draw_l='L',mixed_delivery_l='L',
        scald_exposure_fixture_s='fixture·s',under_temperature_fixture_s='fixture·s',hygiene_band_volume_time_l_s='L·s',maximum_modeled_water_age_s='s',
        minimum_layer_maximum_hot_dwell_s='s',requested_draw_l='L',unmet_draw_l='L',energy_balance_residual_j='J',simulated_duration_s='s',stop_reason='status'),
        [check('temperature_domain',not stop,stop or 'within domain','within domain','status',ref),check('storage_temperature',minstorage>=minimum,minstorage,minimum,'C',ref),
         check('scald_exposure',scald_s==0,scald_s,0,'fixture·s',ref),check('minimum_delivery',under_s==0,under_s,0,'fixture·s',ref),
         check('draw_service',mixed_volume+1e-10>=required_fraction*requested_volume,mixed_volume*1000,required_fraction*requested_volume*1000,'L',ref),
         check('modeled_age',maxage<=age_limit,maxage,age_limit,'s',ref),check('thermal_dwell_candidate',min(maxdwell)>=dwell,min(maxdwell),dwell,'s',ref),
         check('thermal_energy_conservation',abs(residual)<=max(1,abs(heater_j)+abs(out_j))*1e-8,residual,0,'J',ref)],trace,complete=not stop,
        notes=['EXPERIMENTAL constant-volume bottom-to-top stratified layers with makeup, heater hysteresis, interlayer conduction, ambient losses and conservative buoyancy inversion mixing. Separate hot-line cells include draws, stagnation and volume-weighted mean age.',
            'TMV model uses ideal or first-order hot fraction, explicit cold-loss closing delay and delivered-flow reduction. Hardware shutoff/response times are supplied, not certified; no hydraulic pressure/valve-capacity solution or probabilistic mixing-valve failure rate.',
            'Temperature bands, dwell and modeled mean age are risk/validation indicators, not bacterial counts, pathogen kill certification or a hygiene/scald approval. Source thresholds, real commissioning tests, fixture-specific hydraulics and thermal validation remain required.'])
