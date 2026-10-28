"""Source-bound medical-gas demand and low-Mach isothermal tree hydraulics.

No clinical demand, diversity, allowable pressure or adoption is inferred from a
standard name. Reference flow conditions are compulsory, including for vacuum.
"""
import math
from engineering.common import fields, num, text, rows, unique, check, result

BASIS = {
    'HTM_02_01': 'UK HTM 02-01, Part A',
    'SBC_NFPA_99': 'Saudi adopted SBC with project-specified NFPA 99 and HTM references',
    'ISO_7396_1': 'ISO 7396-1, compressed medical gases and vacuum',
}


def medical_gas(data):
    fields(data, 'source_id standard_basis standard_edition precedence_reference service mode '
        'gas_constant_j_kgk gas_temperature_k compressibility heat_capacity_ratio '
        'reference_pressure_absolute_kpa reference_temperature_k reference_compressibility '
        'atmospheric_pressure_kpa source_pressure_absolute_kpa source_node '
        'minimum_terminal_absolute_kpa maximum_terminal_absolute_kpa maximum_velocity_m_s '
        'maximum_mach nodes pipes demand_groups plant_units required_reserve_min reserve_standard_l')
    ref = text(data, 'source_id')
    if data.get('standard_basis') not in BASIS:
        raise ValueError('Select HTM_02_01, SBC_NFPA_99 or ISO_7396_1; standards are not interchangeable')
    edition = text(data, 'standard_edition'); precedence = text(data, 'precedence_reference')
    service = text(data, 'service')
    if service.upper() in ('AGSS', 'N2O', 'CO2'):
        raise ValueError('AGSS and liquefiable-gas services require a service-specific validated model; not supported here')
    mode = data.get('mode')
    if mode not in ('pressure', 'vacuum'): raise ValueError('mode must be pressure or vacuum')
    r = num(data, 'gas_constant_j_kgk', positive=True)
    temp = num(data, 'gas_temperature_k', positive=True)
    z = num(data, 'compressibility', positive=True)
    gamma = num(data, 'heat_capacity_ratio', minimum=1, maximum=2)
    pref = num(data, 'reference_pressure_absolute_kpa', positive=True)*1000
    tref = num(data, 'reference_temperature_k', positive=True)
    zref = num(data, 'reference_compressibility', positive=True)
    ambient = num(data, 'atmospheric_pressure_kpa', positive=True)*1000
    psource = num(data, 'source_pressure_absolute_kpa', positive=True)*1000
    pmin = num(data, 'minimum_terminal_absolute_kpa', positive=True)*1000
    pmax = num(data, 'maximum_terminal_absolute_kpa', positive=True)*1000
    if pmin > pmax: raise ValueError('Terminal pressure range is reversed')
    if mode == 'pressure' and psource <= ambient or mode == 'vacuum' and psource >= ambient:
        raise ValueError('Source absolute pressure does not agree with pressure/vacuum service')
    vmax = num(data, 'maximum_velocity_m_s', positive=True)
    mlimit = num(data, 'maximum_mach', positive=True, maximum=.3)
    nodes = rows(data, 'nodes', limit=500); unique(nodes)
    nodeids = {text(n, 'id') for n in nodes}
    for n in nodes: fields(n, 'id source_id'); text(n, 'source_id')
    root = text(data, 'source_node')
    if root not in nodeids: raise ValueError('Source node is missing')
    pipes = rows(data, 'pipes', limit=499); unique(pipes)
    parents = {}; children = {n: [] for n in nodeids}; byid = {}
    for p in pipes:
        fields(p, 'id source_id from_node to_node length_m internal_mm friction_factor fittings_k')
        a = text(p, 'from_node'); b = text(p, 'to_node'); text(p, 'source_id')
        if a not in nodeids or b not in nodeids or a == b or b in parents or b == root:
            raise ValueError('Pipes must form a tree oriented from plant/source toward terminals, including for vacuum')
        num(p, 'length_m', positive=True); num(p, 'internal_mm', positive=True)
        num(p, 'friction_factor', positive=True, maximum=1); num(p, 'fittings_k', minimum=0)
        parents[b] = a; children[a].append(b); byid[b] = p
    order = [root]
    for a in order:
        order.extend(children[a])
        if len(order) > len(nodes): raise ValueError('Loop detected: medical-gas method supports trees only')
    if len(order) != len(nodes) or len(pipes) != len(nodes)-1:
        raise ValueError('Disconnected nodes or loop: supply a connected tree; loops require a gas solver')
    groups = rows(data, 'demand_groups'); unique(groups)
    demands = {n: 0. for n in nodeids}; group_trace = []
    for g in groups:
        fields(g, 'id source_id node clinical_position positions flow_per_position_lpm diversity continuous_lpm')
        source = text(g, 'source_id'); node = text(g, 'node'); text(g, 'clinical_position')
        if node not in nodeids or node == root: raise ValueError('Each demand group needs a downstream node')
        count = num(g, 'positions', positive=True)
        if int(count) != count: raise ValueError('Clinical position count must be an integer')
        flow = count*num(g, 'flow_per_position_lpm', minimum=0)*num(g, 'diversity', minimum=0, maximum=1)+num(g, 'continuous_lpm', minimum=0)
        demands[node] += flow
        group_trace.append(dict(kind='clinical_demand', id=g['id'], node=node, reference_flow_lpm=flow, source_id=source))
    accumulated = demands.copy()
    for n in reversed(order[1:]): accumulated[parents[n]] += accumulated[n]
    rho_ref = pref/(r*tref*zref); pressures = {root: psource}; trace = group_trace; checks = []
    min_pressure = float('inf'); max_velocity = 0.; max_mach = 0.
    for node in order[1:]:
        p = byid[node]; d = p['internal_mm']/1000; area = math.pi*d*d/4
        mdot = accumulated[node]/60000*rho_ref
        resistance = p['friction_factor']*p['length_m']/d+p['fittings_k']
        delta = resistance*mdot**2*r*temp*z/area**2
        square = pressures[parents[node]]**2 + (delta if mode == 'vacuum' else -delta)
        if square <= 0:
            raise ValueError('Insufficient absolute source pressure at pipe '+p['id']+'; increase bore/source pressure or reduce demand; no choked-flow result is inferred')
        downstream = math.sqrt(square); pressures[node] = downstream
        lowp = min(downstream, pressures[parents[node]])
        velocity = mdot*r*temp*z/(area*lowp)
        mach = velocity/math.sqrt(gamma*r*temp*z)
        max_velocity = max(max_velocity, velocity); max_mach = max(max_mach, mach)
        checks.extend([check(p['id']+':velocity', velocity<=vmax, velocity, vmax, 'm/s', p['source_id']),
            check(p['id']+':low_mach_domain', mach<=mlimit, mach, mlimit, '1', p['source_id'])])
        trace.append(dict(kind='pipe', id=p['id'], reference_flow_lpm=accumulated[node], mass_flow_kg_s=mdot,
            upstream_absolute_kpa=pressures[parents[node]]/1000, downstream_absolute_kpa=downstream/1000,
            peak_velocity_m_s=velocity, mach=mach, source_id=p['source_id']))
    for node in sorted(n for n in nodeids if demands[n]>0):
        p = pressures[node]; min_pressure = min(min_pressure, p)
        valid = pmin<=p<=pmax and (p>=ambient if mode=='pressure' else p<=ambient)
        checks.append(check(node+':terminal_pressure', valid, p/1000, [pmin/1000,pmax/1000], 'kPa absolute', ref))
    units = rows(data, 'plant_units', empty=True, limit=50); unique(units)
    capacities = []
    for u in units:
        fields(u, 'id source_id reference_capacity_lpm available'); text(u, 'source_id')
        from engineering.common import flag
        if flag(u, 'available'): capacities.append(num(u, 'reference_capacity_lpm', minimum=0))
        else: num(u, 'reference_capacity_lpm', minimum=0)
    duty = accumulated[root]; nminus1 = sum(capacities)-max(capacities, default=0)
    reserve = num(data, 'reserve_standard_l', minimum=0)
    required_reserve = num(data, 'required_reserve_min', minimum=0)
    duration = reserve/duty if duty else 0
    checks.extend([check('plant_largest_unit_unavailable', nminus1>=duty, nminus1, duty, 'reference L/min', ref),
        check('reserve_duration', duration>=required_reserve, duration, required_reserve, 'min', ref)])
    if duty<=0: raise ValueError('Supply at least one positive clinical demand')
    return result(dict(design_reference_flow_lpm=duty, mass_flow_kg_s=duty/60000*rho_ref,
        minimum_terminal_absolute_kpa=min_pressure/1000, maximum_velocity_m_s=max_velocity, maximum_mach=max_mach,
        plant_n_minus_one_capacity_lpm=nminus1, reserve_duration_min=duration),
        dict(design_reference_flow_lpm='reference L/min', mass_flow_kg_s='kg/s', minimum_terminal_absolute_kpa='kPa absolute',
            maximum_velocity_m_s='m/s', maximum_mach='1', plant_n_minus_one_capacity_lpm='reference L/min', reserve_duration_min='min'),
        checks, trace, complete=max_mach<=.3,
        notes=[BASIS[data['standard_basis']]+'; edition as supplied: '+edition+'; precedence: '+precedence,
            'Clinical position demand and diversity are supplied criteria, not automatic code-table values. Reference pressure/temperature/Z define all L/min and reserve quantities.',
            'Isothermal, constant-Z, prescribed-Darcy-factor low-Mach model; elevation and acceleration neglected. Vacuum pipes are oriented plant to terminal; actual flow is toward plant.',
            'Adoption, clinical approval, gas purity, cross-connection, alarms, zone isolation, material/cleanliness, commissioning and gas-specific certified plant performance remain unevaluated.'])
