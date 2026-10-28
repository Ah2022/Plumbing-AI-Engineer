"""Supplied fire-duty checks and explicit contamination-path separation screening."""
from collections import deque
from engineering.common import fields,num,text,rows,unique,check,result


def fire_separation(data):
    fields(data,'source_id separation_policy nodes links available_fire_flow_lps required_fire_flow_lps available_fire_pressure_m required_fire_pressure_m tank_usable_m3 domestic_reserved_m3 fire_reserved_m3 required_fire_storage_m3')
    ref=text(data,'source_id');policy=data.get('separation_policy')
    if policy not in ('separate_systems','shared_supply_with_backflow'):raise ValueError('Explicit reviewed separation policy is required')
    nodes=rows(data,'nodes');links=rows(data,'links',empty=True);unique(nodes);unique(links)
    byid={n['id']:n for n in nodes};directed={n:set() for n in byid};undirected={n:set() for n in byid}
    for n in nodes:
        fields(n,'id service source_id');text(n,'source_id')
        if n.get('service') not in ('domestic','fire','shared'):raise ValueError('Node service must be domestic/fire/shared')
    for link in links:
        fields(link,'id from_node to_node barrier source_id');text(link,'source_id');a,b=link.get('from_node'),link.get('to_node')
        if a not in byid or b not in byid or a==b:raise ValueError('Invalid separation link endpoints')
        barrier=link.get('barrier')
        if barrier not in ('none','reviewed_one_way_backflow','reviewed_air_gap'):raise ValueError('Explicit reviewed barrier type is required')
        directed[a].add(b)
        if barrier=='none':directed[b].add(a)
        undirected[a].add(b);undirected[b].add(a)
    domestic=[n for n in byid if byid[n]['service']=='domestic'];fire=[n for n in byid if byid[n]['service']=='fire']
    if not domestic or not fire:raise ValueError('Classify at least one domestic and one fire node')
    def path(start,end,adj):
        queue=deque([(start,[start])]);seen={start}
        while queue:
            node,route=queue.popleft()
            if node==end:return route
            for nxt in sorted(adj[node]):
                if nxt not in seen:seen.add(nxt);queue.append((nxt,route+[nxt]))
        return None
    paths=[];adj=undirected if policy=='separate_systems' else directed
    for start in fire:
        for end in domestic:
            route=path(start,end,adj)
            if route:paths.append(dict(from_fire=start,to_domestic=end,path=route))
    available=num(data,'available_fire_flow_lps',minimum=0);required=num(data,'required_fire_flow_lps',positive=True)
    pressure=num(data,'available_fire_pressure_m');minimum=num(data,'required_fire_pressure_m',minimum=0)
    tank=num(data,'tank_usable_m3',minimum=0);domreserve=num(data,'domestic_reserved_m3',minimum=0);firereserve=num(data,'fire_reserved_m3',minimum=0);firestorage=num(data,'required_fire_storage_m3',minimum=0)
    checks=[check('separation_paths',not paths,len(paths),0,'paths',ref),check('supplied_fire_flow',available>=required,available,required,'L/s',ref),
        check('supplied_fire_pressure',pressure>=minimum,pressure,minimum,'m',ref),check('reserved_volumes_do_not_overlap',domreserve+firereserve<=tank,domreserve+firereserve,tank,'m3',ref),
        check('dedicated_fire_storage',firereserve>=firestorage,firereserve,firestorage,'m3',ref)]
    return result({'fire_flow_margin_lps':available-required,'fire_pressure_margin_m':pressure-minimum,'unprotected_paths':len(paths),
        'unallocated_storage_m3':tank-domreserve-firereserve},{'fire_flow_margin_lps':'L/s','fire_pressure_margin_m':'m','unprotected_paths':'count','unallocated_storage_m3':'m3'},checks,paths,
        notes=['Fire flow/pressure must be simultaneous results from the reviewed hydraulic scenario. Barriers are user-attributed directional review assertions; this is not a device listing/test, fire-code certification or backflow assembly approval. Fire storage/flow duration and NFPA/local requirements must be supplied and independently verified.'])
