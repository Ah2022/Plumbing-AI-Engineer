"""Single-circuit system curves and catalogue interpolation, with no extrapolation."""
import math
from engineering.common import fields,num,text,rows,unique,check,result,interpolate,G


def validate_curve(points):
    if not isinstance(points,list) or not 2<=len(points)<=1000:raise ValueError('A bounded H-Q curve with at least two points is required')
    q=-1;head=math.inf
    for p in points:
        fields(p,'flow_lps head_m');nq=num(p,'flow_lps',minimum=0);nh=num(p,'head_m',minimum=0)
        if nq<=q or nh>=head:raise ValueError('Pump flow must increase and head decrease strictly')
        q,head=nq,nh


def operating_point(data):
    fields(data,'source_id static_head_m resistance_m_per_lps2 pump_curve sample_flows_lps')
    ref=text(data,'source_id');static=num(data,'static_head_m',minimum=0);resistance=num(data,'resistance_m_per_lps2',minimum=0)
    curve=data.get('pump_curve');validate_curve(curve)
    def system(q):return static+resistance*q*q
    def difference(q):return interpolate(curve,q,'flow_lps','head_m')-system(q)
    lo,hi=curve[0]['flow_lps'],curve[-1]['flow_lps']
    samples=data.get('sample_flows_lps')
    if not isinstance(samples,list) or not 1<=len(samples)<=200:raise ValueError('Supply 1–200 system-curve sample flows')
    trace=[]
    for q in samples:
        num({'q':q},'q',minimum=0)
        trace.append(dict(flow_lps=q,system_head_m=system(q),pump_head_m=interpolate(curve,q,'flow_lps','head_m') if lo<=q<=hi else None))
    if difference(lo)<0 or difference(hi)>0:
        return result({'operating_flow_lps':None,'operating_head_m':None},{'operating_flow_lps':'L/s','operating_head_m':'m'},trace=trace,complete=False,
            notes=['No operating intersection within the supplied pump curve; extend authenticated source data or revise the system. No curve extrapolation performed.'])
    for _ in range(100):
        mid=(lo+hi)/2
        if difference(mid)>0:lo=mid
        else:hi=mid
    q=(lo+hi)/2;head=system(q)
    return result({'operating_flow_lps':q,'operating_head_m':head,'head_balance_residual_m':difference(q)},
        {'operating_flow_lps':'L/s','operating_head_m':'m','head_balance_residual_m':'m'},
        [check('intersection_inside_source_curve',True,q,[curve[0]['flow_lps'],curve[-1]['flow_lps']],'L/s',ref)],trace,
        notes=['Quadratic single-circuit system and piecewise-linear manufacturer H-Q interpolation. EPANET three-point power-curve fitting is a separate model.'])


def equipment_selection(data):
    fields(data,'source_id equipment_kind duty_flow_lps duty_head_m required_usable_volume_l design_pressure_kpa design_temperature_c fluid npsha_m required_npsh_margin_m catalogue')
    ref=text(data,'source_id');kind=data.get('equipment_kind');fluid=text(data,'fluid')
    if kind not in ('pump','tank'):raise ValueError('Supported catalogue kinds are pump and tank')
    pressure=num(data,'design_pressure_kpa',minimum=0);temp=num(data,'design_temperature_c',minimum=-273.15)
    catalogue=rows(data,'catalogue',limit=500);unique(catalogue,'model_id');evaluations=[];matches=[]
    if kind=='pump':
        flow=num(data,'duty_flow_lps',minimum=0);head=num(data,'duty_head_m',minimum=0)
        npsha=num(data,'npsha_m',minimum=0);margin=num(data,'required_npsh_margin_m',minimum=0)
    else:required=num(data,'required_usable_volume_l',positive=True)
    for entry in catalogue:
        fields(entry,'model_id manufacturer source_id fluid max_pressure_kpa min_temperature_c max_temperature_c pump_curve efficiency npshr_m usable_volume_l')
        model=text(entry,'model_id');text(entry,'manufacturer');text(entry,'source_id');reasons=[]
        maxp=num(entry,'max_pressure_kpa',positive=True);mint=num(entry,'min_temperature_c',minimum=-273.15);maxt=num(entry,'max_temperature_c',minimum=-273.15)
        if mint>maxt:raise ValueError('Inverted manufacturer temperature range')
        if entry.get('fluid')!=fluid:reasons.append('Fluid/service designation differs')
        if pressure>maxp:reasons.append('Pressure rating insufficient')
        if not mint<=temp<=maxt:reasons.append('Temperature outside rating')
        row=dict(model_id=model,manufacturer=entry['manufacturer'],source_id=entry['source_id'])
        if kind=='pump':
            validate_curve(entry.get('pump_curve'));eta=num(entry,'efficiency',positive=True,maximum=1);npshr=num(entry,'npshr_m',minimum=0)
            if not entry['pump_curve'][0]['flow_lps']<=flow<=entry['pump_curve'][-1]['flow_lps']:reasons.append('Duty flow outside published curve; no extrapolation')
            else:
                available=interpolate(entry['pump_curve'],flow,'flow_lps','head_m');row['available_head_m']=available
                if available<head:reasons.append('Head at duty flow insufficient')
                row['head_margin_m']=available-head
            if npsha<npshr+margin:reasons.append('NPSH margin insufficient')
            row['duty_input_power_kw']=1000*G*(flow/1000)*head/(eta*1000)
        else:
            usable=num(entry,'usable_volume_l',positive=True);row['usable_volume_l']=usable
            if usable<required:reasons.append('Usable storage insufficient')
        row.update(eligible=not reasons,rejection_reasons=reasons);evaluations.append(row)
        if not reasons:matches.append(model)
    return result({'eligible_models':matches,'eligible_count':len(matches)}, {'eligible_models':'model IDs','eligible_count':'count'},
        [check('catalogue_candidates_meet_supplied_duty',bool(matches),len(matches),'>=1','count',ref)],evaluations,
        notes=['Candidates are screened, not automatically purchased/approved. Pump trim, preferred operating region, viscosity corrections and certified NPSHr/efficiency at the actual duty still require manufacturer/engineer review.'])
