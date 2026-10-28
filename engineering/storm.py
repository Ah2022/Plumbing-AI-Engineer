"""Bounded single-storage level-pool routing by the Modified Puls equation."""
from engineering.common import fields,num,text,rows,result,check,interpolate


def route_storage(data):
    fields(data,'source_id initial_storage_m3 maximum_permitted_level_m storage_rating hydrograph')
    ref=text(data,'source_id');initial=num(data,'initial_storage_m3',minimum=0);limit=num(data,'maximum_permitted_level_m')
    rating=rows(data,'storage_rating');hydro=rows(data,'hydrograph',limit=10000)
    if len(rating)<2 or len(hydro)<2:raise ValueError('At least two storage-rating and hydrograph records are required')
    last_level=last_storage=None;last_out=-1
    for row in rating:
        fields(row,'level_m storage_m3 outflow_lps');level=num(row,'level_m');storage=num(row,'storage_m3',minimum=0);out=num(row,'outflow_lps',minimum=0)
        if last_level is not None and (level<=last_level or storage<=last_storage) or out<last_out:raise ValueError('Level/storage must increase strictly and outflow must not decrease')
        last_level,last_storage,last_out=level,storage,out
    if rating[0]['storage_m3']!=0 or rating[0]['outflow_lps']!=0:raise ValueError('Rating must begin at zero active storage and zero outflow')
    if not rating[0]['storage_m3']<=initial<=rating[-1]['storage_m3']:raise ValueError('Initial storage outside supplied rating')
    if not rating[0]['level_m']<=limit<=rating[-1]['level_m']:raise ValueError('Permitted level outside supplied rating')
    previous=-1
    for row in hydro:
        fields(row,'time_s inflow_lps');time=num(row,'time_s',minimum=0);num(row,'inflow_lps',minimum=0)
        if time<=previous:raise ValueError('Hydrograph times must increase strictly')
        previous=time
    if hydro[0]['time_s']!=0:raise ValueError('Hydrograph must start at time zero')
    storage=initial;out=interpolate(rating,storage,'storage_m3','outflow_lps')/1000;level=interpolate(rating,storage,'storage_m3','level_m')
    trace=[dict(time_s=0,storage_m3=storage,level_m=level,outflow_lps=out*1000,inflow_lps=hydro[0]['inflow_lps'],mass_balance_residual_m3=0)]
    cumulative_in=cumulative_out=0;complete=True;excess=0
    for a,b in zip(hydro,hydro[1:]):
        dt=b['time_s']-a['time_s'];in_volume=(a['inflow_lps']+b['inflow_lps'])/2000*dt
        target=2*storage/dt-out+(a['inflow_lps']+b['inflow_lps'])/1000
        transformed=[dict(storage_m3=r['storage_m3'],target=2*r['storage_m3']/dt+r['outflow_lps']/1000) for r in rating]
        dry=target<0
        if target>transformed[-1]['target']:
            excess=(target-transformed[-1]['target'])*dt/2;complete=False
            break
        next_storage=0 if dry else interpolate(transformed,target,'target','storage_m3')
        next_out=interpolate(rating,next_storage,'storage_m3','outflow_lps')/1000
        released=storage+in_volume-next_storage if dry else (out+next_out)/2*dt
        residual=storage+in_volume-released-next_storage
        cumulative_in+=in_volume;cumulative_out+=released
        storage=next_storage;out=next_out;level=interpolate(rating,storage,'storage_m3','level_m')
        trace.append(dict(time_s=b['time_s'],inflow_lps=b['inflow_lps'],outflow_lps=out*1000,storage_m3=storage,level_m=level,
            released_volume_m3=released,dry_outflow_limited=dry,mass_balance_residual_m3=residual))
    peak=max(r['level_m'] for r in trace)
    return result({'peak_computed_level_m':peak,'final_computed_storage_m3':storage,'routed_inflow_volume_m3':cumulative_in,
        'routed_outflow_volume_m3':cumulative_out,'unrouted_excess_at_first_failure_m3':excess,
        'overall_mass_balance_residual_m3':initial+cumulative_in-cumulative_out-storage},
        {'peak_computed_level_m':'m','final_computed_storage_m3':'m3','routed_inflow_volume_m3':'m3','routed_outflow_volume_m3':'m3',
         'unrouted_excess_at_first_failure_m3':'m3','overall_mass_balance_residual_m3':'m3'},
        [check('storage_rating_range',complete,excess,0,'m3',ref),check('permitted_level',peak<=limit,peak,limit,'m',ref)],trace,complete=complete,
        notes=['Modified Puls single level-pool storage with monotone user rating and linearly varying inflow. Dry storage limits release by available water. Routing stops if the rating range is exceeded; excess is not presented as a physically routed overflow. Rainfall-runoff generation, tailwater coupling and distributed sewer routing are separate.'])
