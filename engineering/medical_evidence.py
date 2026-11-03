"""AGSS interface checks, liquid-source inventory and commissioning evidence.

Acceptance is always pending; no software operation issues a medical certificate.
"""
import datetime
from engineering.common import fields,num,text,rows,unique,flag,check,result


def agss_network(data):
    fields(data,'source_id network interfaces exhaust_evidence_reference')
    ref=text(data,'source_id');text(data,'exhaust_evidence_reference')
    from engineering.medical_gas import _gas_network
    network=data.get('network');output=_gas_network(network,agss=True)
    interfaces=rows(data,'interfaces',limit=100);unique(interfaces,'node')
    pipes={p['to_node']:p['id'] for p in network['pipes']};pressure={r['id']:r['downstream_absolute_kpa'] for r in output['trace'] if r.get('kind')=='pipe'}
    demand_nodes={r['node'] for r in network['demand_groups']}
    if {r['node'] for r in interfaces}!=demand_nodes:raise ValueError('Every AGSS demand node requires an interface record; no duplicate or unassigned interfaces')
    outgoing={p['from_node'] for p in network['pipes']}
    for interface in interfaces:
        fields(interface,'node source_id minimum_reference_flow_lpm maximum_reference_flow_lpm minimum_suction_kpa maximum_suction_kpa interface_listing_reference')
        source=text(interface,'source_id');node=text(interface,'node');text(interface,'interface_listing_reference')
        if node in outgoing:raise ValueError('This AGSS interface prototype requires terminal demand nodes, not demands at shared junctions')
        lo=num(interface,'minimum_reference_flow_lpm',minimum=0);hi=num(interface,'maximum_reference_flow_lpm',positive=True)
        pmin=num(interface,'minimum_suction_kpa',minimum=0);pmax=num(interface,'maximum_suction_kpa',positive=True)
        if lo>hi or pmin>pmax:raise ValueError('AGSS interface criterion range reversed')
        flow=sum(r['reference_flow_lpm'] for r in output['trace'] if r.get('kind')=='clinical_demand' and r['node']==node)
        suction=network['atmospheric_pressure_kpa']-pressure[pipes[node]]
        output['checks'].extend([check(node+':AGSS_interface_flow',lo<=flow<=hi,flow,[lo,hi],'reference L/min',source),
            check(node+':AGSS_interface_suction',pmin<=suction<=pmax,suction,[pmin,pmax],'kPa below atmosphere',source)])
        output['trace'].append(dict(kind='AGSS_interface',id=node,reference_flow_lpm=flow,suction_kpa=suction,source_id=source))
    output['notes']+=['AGSS interface/plant network only. Interface-specific flow/suction, air-break/protection listing and exhaust evidence are mandatory inputs; no values are borrowed from medical vacuum terminal criteria.',
        'Patient breathing-circuit interaction, room exposure/dispersion, actual capture efficiency, noise, terminal tests and commissioning certification remain outside this hydraulic prototype.']
    return output


def liquid_gas_inventory(data):
    fields(data,'source_id service source_approval_reference tank_liquid_l fill_fraction unusable_fraction '
        'liquid_density_kg_l reference_gas_density_kg_m3 peak_reference_flow_lpm average_reference_flow_lpm '
        'required_reserve_h latent_heat_j_kg parasitic_heat_w vaporizers')
    ref=text(data,'source_id');service=text(data,'service');text(data,'source_approval_reference')
    if service not in ('O2','N2','N2O','CO2'):raise ValueError('Declare O2, N2, N2O or CO2 liquid source; no generic phase properties are inferred')
    tank=num(data,'tank_liquid_l',positive=True);fill=num(data,'fill_fraction',positive=True,maximum=1);unusable=num(data,'unusable_fraction',minimum=0,maximum=1)
    if fill<=unusable:raise ValueError('Tank fill must exceed unusable fraction')
    density=num(data,'liquid_density_kg_l',positive=True);gas=num(data,'reference_gas_density_kg_m3',positive=True)
    peak=num(data,'peak_reference_flow_lpm',positive=True);average=num(data,'average_reference_flow_lpm',positive=True)
    if average>peak:raise ValueError('Average demand cannot exceed declared peak')
    hours=num(data,'required_reserve_h',positive=True);latent=num(data,'latent_heat_j_kg',positive=True);heat=num(data,'parasitic_heat_w',minimum=0)
    units=rows(data,'vaporizers',limit=30);unique(units);capacities=[];trace=[]
    for unit in units:
        fields(unit,'id source_id available rated_mass_kg_h rated_heat_w rating_condition_reference');source=text(unit,'source_id');text(unit,'rating_condition_reference')
        mass=num(unit,'rated_mass_kg_h',positive=True);power=num(unit,'rated_heat_w',positive=True)
        usable=min(mass,power/latent*3600)
        if flag(unit,'available'):capacities.append(usable)
        trace.append(dict(id=unit['id'],usable_mass_capacity_kg_h=usable,available=unit['available'],source_id=source))
    available=sum(capacities)-max(capacities,default=0);peakmass=peak/1000*60*gas
    inventory=tank*(fill-unusable)*density;boiloff=heat/latent*3600
    average_mass=average/1000*60*gas;reserve=inventory/(average_mass+boiloff)
    return result(dict(usable_liquid_mass_kg=inventory,usable_reference_gas_m3=inventory/gas,peak_mass_demand_kg_h=peakmass,
        n_minus_one_vaporization_kg_h=available,estimated_unrecovered_boiloff_kg_h=boiloff,reserve_duration_h=reserve),
        dict(usable_liquid_mass_kg='kg',usable_reference_gas_m3='reference m³',peak_mass_demand_kg_h='kg/h',n_minus_one_vaporization_kg_h='kg/h',
            estimated_unrecovered_boiloff_kg_h='kg/h',reserve_duration_h='h'),
        [check('liquid_inventory_reserve',reserve>=hours,reserve,hours,'h',ref),check('vaporizer_largest_unit_unavailable',available>=peakmass,available,peakmass,'kg/h',ref)],trace,
        notes=['Inventory/energy capacity calculation with supplied liquid/reference-gas densities, latent heat, unusable stock, demand and ambient-condition vaporizer ratings. All parasitic heat is conservatively treated as unrecovered boiloff; actual recovery/control must be reviewed.',
            'No two-phase pipe pressure-drop, phase-equilibrium/refrigeration, icing/de-rating curve, relief venting, oxygen compatibility, CO2 dry-ice formation or N2O decomposition model. Supplier authorization, site risk assessment, actual gas purity and certified plant commissioning remain required.'])


def medical_commissioning(data):
    fields(data,'source_id standard_reference adopted_edition system_revision evaluation_date required_tests measurements signoffs required_roles')
    ref=text(data,'source_id');text(data,'standard_reference');text(data,'adopted_edition');revision=text(data,'system_revision')
    try:today=datetime.date.fromisoformat(text(data,'evaluation_date'))
    except ValueError as e:raise ValueError('Evaluation date must be ISO YYYY-MM-DD') from e
    required=rows(data,'required_tests',limit=200);unique(required);measurements=rows(data,'measurements',empty=True,limit=500);unique(measurements,'test_id')
    signoffs=rows(data,'signoffs',empty=True,limit=50);unique(signoffs,'role');roles=data.get('required_roles')
    if not isinstance(roles,list) or not roles or not all(isinstance(r,str) and r.strip() for r in roles) or len(set(roles))!=len(roles):raise ValueError('Supply explicit unique required commissioning roles')
    kinds={'identity','cross_connection','pressure','leakage','particles','gas_quality','alarm','plant','AGSS','liquid_source','other'}
    ids={r['id'] for r in required};byid={m['test_id']:m for m in measurements};checks=[];trace=[];missing=0
    if set(byid)-ids:raise ValueError('A measurement refers to a test outside the declared commissioning scope')
    for test in required:
        fields(test,'id source_id kind location unit minimum maximum maximum_uncertainty required_method');source=text(test,'source_id')
        if test.get('kind') not in kinds:raise ValueError('Unsupported commissioning test kind')
        text(test,'location');text(test,'unit');text(test,'required_method')
        low=num(test,'minimum');high=num(test,'maximum');unc=num(test,'maximum_uncertainty',minimum=0)
        if low>high:raise ValueError('Test range reversed')
        m=byid.get(test['id'])
        if m is None:
            missing+=1;trace.append(dict(id=test['id'],kind=test['kind'],status='MISSING_MEASUREMENT'));continue
        fields(m,'test_id source_id value uncertainty unit method location system_revision measured_on calibration_valid_until operator laboratory evidence_reference')
        text(m,'source_id');text(m,'operator');text(m,'laboratory');text(m,'evidence_reference')
        value=num(m,'value');u=num(m,'uncertainty',minimum=0)
        try:measured=datetime.date.fromisoformat(text(m,'measured_on'));expires=datetime.date.fromisoformat(text(m,'calibration_valid_until'))
        except ValueError as e:raise ValueError('Measurement/calibration dates must be ISO YYYY-MM-DD') from e
        valid=(low<=value-u and value+u<=high and u<=unc and m['unit']==test['unit'] and m['method']==test['required_method']
            and m['location']==test['location'] and m['system_revision']==revision and measured<=today<=expires)
        checks.append(check(test['id']+':measured_test_envelope',valid,[value-u,value+u],[low,high],test['unit'],source))
        trace.append(dict(id=test['id'],kind=test['kind'],status='REPORTED_WITHIN_CRITERIA' if valid else 'FAIL_OR_STALE_EVIDENCE',source_id=m['source_id']))
    signby={s['role']:s for s in signoffs};pending=[]
    if set(signby)-set(roles):raise ValueError('Signoff role is outside the declared commissioning scope')
    for role in roles:
        s=signby.get(role)
        if s is None:pending.append(role);continue
        fields(s,'role source_id name credential_reference appointment_reference system_revision signed_on evidence_reference')
        for key in ('source_id','name','credential_reference','appointment_reference','signed_on','evidence_reference'):text(s,key)
        try:date=datetime.date.fromisoformat(s['signed_on'])
        except ValueError as e:raise ValueError('Signoff date must be ISO YYYY-MM-DD') from e
        if s.get('system_revision')!=revision or date>today:pending.append(role)
    complete=missing==0 and not pending
    checks.append(check('declared_evidence_scope_complete',complete,dict(missing_tests=missing,pending_roles=pending),dict(missing_tests=0,pending_roles=[]),'evidence',ref))
    return result(dict(required_test_count=len(required),reported_test_count=len(measurements),missing_test_count=missing,pending_roles=pending,
        certification_status='NOT_ISSUED',signature_authenticity='NOT_ESTABLISHED_BY_THIS_CHECK'),
        dict(required_test_count='count',reported_test_count='count',missing_test_count='count',pending_roles='roles',certification_status='status',signature_authenticity='status'),checks,trace,
        complete=complete,notes=['Commissioning scope, numerical gas-quality/test criteria, required methods/units/locations, uncertainty and required roles are explicitly supplied; no pharmacopoeia limits are invented. The full uncertainty interval must fit within the supplied range.',
            'This audits reported measurements, calibration validity, model revision and signoff completeness. Documentary signatures, identity, appointments, competence, laboratory accreditation, gas quality on site and actual test execution need external verification.',
            'Even complete evidence does not issue a medical-gas certificate. Authorized clinical/technical personnel and the applicable jurisdiction retain commissioning and certification authority.'])
