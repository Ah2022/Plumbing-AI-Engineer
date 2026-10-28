"""Steady no-draw thermal recirculation and parallel-loop hydraulic balancing."""
import math
from engineering.common import fields,num,text,rows,unique,check,result,G


def recirculation(data):
    fields(data,'source_id supply_temperature_c minimum_return_temperature_c water_density_kg_m3 specific_heat_j_kgk branches')
    ref=text(data,'source_id');supply=num(data,'supply_temperature_c',minimum=-273.15);minimum=num(data,'minimum_return_temperature_c',minimum=-273.15)
    if minimum>=supply:raise ValueError('Return target must be below supply temperature')
    rho=num(data,'water_density_kg_m3',positive=True);cp=num(data,'specific_heat_j_kgk',positive=True)
    branches=rows(data,'branches',limit=100);unique(branches);trace=[];checks=[]
    for branch in branches:
        fields(branch,'id source_id length_m heat_loss_w_m selected_flow_lps internal_mm friction_factor fittings_k balancing_loss_m')
        identity=text(branch,'id');source=text(branch,'source_id');length=num(branch,'length_m',positive=True);loss_per_m=num(branch,'heat_loss_w_m',minimum=0)
        selected=num(branch,'selected_flow_lps',positive=True);d=num(branch,'internal_mm',positive=True)/1000
        f=num(branch,'friction_factor',positive=True);k=num(branch,'fittings_k',minimum=0);balance=num(branch,'balancing_loss_m',minimum=0)
        heat=length*loss_per_m;required=heat/(rho*cp*(supply-minimum))*1000
        returning=supply-heat/(rho*cp*(selected/1000));v=selected/1000/(math.pi*d*d/4)
        head=(f*length/d+k)*v*v/(2*G)+balance
        checks.append(check(identity+':return_temperature',returning>=minimum,returning,minimum,'C',source))
        trace.append(dict(id=identity,heat_loss_w=heat,required_flow_lps=required,selected_flow_lps=selected,return_temperature_c=returning,velocity_m_s=v,loop_head_m=head,source_id=source))
    governing=max(r['loop_head_m'] for r in trace)
    for row in trace:row['additional_balancing_head_m']=governing-row['loop_head_m']
    return result({'total_heat_loss_w':sum(r['heat_loss_w'] for r in trace),'required_total_flow_lps':sum(r['required_flow_lps'] for r in trace),
        'selected_total_flow_lps':sum(r['selected_flow_lps'] for r in trace),'governing_loop_head_m':governing},
        {'total_heat_loss_w':'W','required_total_flow_lps':'L/s','selected_total_flow_lps':'L/s','governing_loop_head_m':'m'},checks,trace,
        notes=['Each branch is a complete parallel circulation loop, including its supply/return heat loss and resistance. Shared-trunk loss must be added separately; static elevation is not added to a closed circulation loop. Fixed heat losses and no draw are assumed. Mixing, hygiene, commissioning and transient thermal behavior are unevaluated.'])
