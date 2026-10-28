"""Uniform open-channel flow and explicit, bounded protection screens."""
import math
from engineering.common import fields,num,text,rows,unique,flag,check,result,G


def circular_section(diameter_m,depth_m):
    if depth_m<=0:return dict(area_m2=0,wetted_perimeter_m=0,hydraulic_radius_m=0)
    theta=2*math.acos(max(-1,min(1,1-2*depth_m/diameter_m)))
    segment=theta**3/6-theta**5/120+theta**7/5040 if theta<.001 else theta-math.sin(theta)
    area=diameter_m**2/8*segment;perimeter=diameter_m*theta/2
    if perimeter==0:return dict(area_m2=0,wetted_perimeter_m=0,hydraulic_radius_m=0)
    return dict(area_m2=area,wetted_perimeter_m=perimeter,hydraulic_radius_m=area/perimeter)


def gravity_flow(data):
    fields(data,'source_id internal_mm slope_pct manning_n design_flow_lps maximum_fill_ratio minimum_velocity_m_s')
    ref=text(data,'source_id');d=num(data,'internal_mm',positive=True)/1000;slope=num(data,'slope_pct',positive=True)/100
    n=num(data,'manning_n',positive=True);flow=num(data,'design_flow_lps',minimum=0);fill=num(data,'maximum_fill_ratio',positive=True,maximum=.9)
    minimum=num(data,'minimum_velocity_m_s',minimum=0)
    def capacity(y):
        section=circular_section(d,y)
        return section['area_m2']*section['hydraulic_radius_m']**(2/3)*math.sqrt(slope)/n*1000
    capacity_at_limit=capacity(d*fill)
    if flow>capacity_at_limit:
        return result({'capacity_at_fill_limit_lps':capacity_at_limit,'normal_depth_m':None,'velocity_m_s':None},
            {'capacity_at_fill_limit_lps':'L/s','normal_depth_m':'m','velocity_m_s':'m/s'},
            [check('capacity_within_fill_limit',False,flow,capacity_at_limit,'L/s',ref)],complete=False,
            notes=['Design flow exceeds the explicitly limited free-surface branch. No surcharged/full-pipe flow or guessed depth is substituted.'])
    lo,hi=0,d*fill
    for _ in range(100):
        mid=(lo+hi)/2
        if capacity(mid)<flow:lo=mid
        else:hi=mid
    y=0 if flow==0 else (lo+hi)/2;section=circular_section(d,y)
    velocity=flow/1000/section['area_m2'] if section['area_m2'] else 0
    return result(dict(capacity_at_fill_limit_lps=capacity_at_limit,normal_depth_m=y,fill_ratio=y/d,velocity_m_s=velocity,**section),
        dict(capacity_at_fill_limit_lps='L/s',normal_depth_m='m',fill_ratio='-',velocity_m_s='m/s',area_m2='m2',wetted_perimeter_m='m',hydraulic_radius_m='m'),
        [check('minimum_velocity_screen',velocity>=minimum,velocity,minimum,'m/s',ref)],
        notes=['Manning steady uniform circular-pipe flow on the lower free-surface branch; maximum fill limited to0.9 to avoid the nonmonotonic near-full branch. No DFU-to-flow inference, unsteady sewer network, junction loss or self-cleansing certification.'])


def fixture_minimum(data):
    fields(data,'source_id fixtures');ref=text(data,'source_id');fixtures=rows(data,'fixtures');unique(fixtures);checks=[];trace=[]
    for f in fixtures:
        fields(f,'id source_id selected_nominal_mm selected_internal_mm required_nominal_mm design_flow_lps minimum_flow_lps available_pressure_m minimum_pressure_m')
        source=text(f,'source_id');identity=text(f,'id');nominal=num(f,'selected_nominal_mm',positive=True);bore=num(f,'selected_internal_mm',positive=True)
        required=num(f,'required_nominal_mm',positive=True);flow=num(f,'design_flow_lps',minimum=0);minflow=num(f,'minimum_flow_lps',minimum=0)
        pressure=num(f,'available_pressure_m');minpressure=num(f,'minimum_pressure_m',minimum=0)
        checks += [check(identity+':nominal_connection',nominal>=required,nominal,required,'nominal mm',source),
            check(identity+':required_flow',flow>=minflow,flow,minflow,'L/s',source),check(identity+':outlet_pressure',pressure>=minpressure,pressure,minpressure,'m',source)]
        trace.append(dict(id=identity,nominal_mm=nominal,internal_mm=bore,nominal_margin_mm=nominal-required,flow_margin_lps=flow-minflow,pressure_margin_m=pressure-minpressure,source_id=source))
    return result({'fixtures_checked':len(fixtures)},{'fixtures_checked':'count'},checks,trace,
        notes=['Required nominal designation must already be mapped from the adopted source/manufacturer; source inches are not automatically equated to DN. Internal bore is recorded separately. Fixture family, appliance listing and simultaneous network demand remain separate checks.'])


def trap_pressure(data):
    fields(data,'source_id initial_seal_mm evaporation_mm_day exposure_days minimum_seal_mm peak_positive_pressure_pa peak_negative_pressure_pa allowable_pressure_pa water_density_kg_m3')
    ref=text(data,'source_id');seal=num(data,'initial_seal_mm',positive=True);rate=num(data,'evaporation_mm_day',minimum=0);days=num(data,'exposure_days',minimum=0)
    minimum=num(data,'minimum_seal_mm',positive=True);positive=num(data,'peak_positive_pressure_pa',minimum=0);negative=num(data,'peak_negative_pressure_pa',minimum=0)
    allowable=num(data,'allowable_pressure_pa',positive=True);rho=num(data,'water_density_kg_m3',positive=True)
    remaining=max(0,seal-rate*days);peak=max(positive,negative);pressure_head=peak/(rho*G)*1000
    return result({'estimated_remaining_seal_mm':remaining,'pressure_equivalent_water_head_mm':pressure_head,
        'pressure_limit_margin_pa':allowable-peak,'initial_hydrostatic_head_pa':rho*G*seal/1000},
        {'estimated_remaining_seal_mm':'mm','pressure_equivalent_water_head_mm':'mm water','pressure_limit_margin_pa':'Pa','initial_hydrostatic_head_pa':'Pa'},
        [check('remaining_seal_after_supplied_evaporation',remaining>=minimum,remaining,minimum,'mm',ref),check('supplied_air_pressure_budget',peak<=allowable,peak,allowable,'Pa',ref)],
        notes=['Pressure peaks must be supplied by measurement or an independently validated air-pressure model. Hydrostatic equivalent is not a trap-break prediction: trap geometry, oscillation, siphonage, momentum and two-phase air/water transients are not solved. Evaporation is a constant-rate screening assumption.'])


def vent_arrangement(data):
    fields(data,'source_id arrangement fixtures selected_vent_nominal_mm required_vent_nominal_mm maximum_fixtures maximum_dfu allowed_fixture_types minimum_clearance_mm actual_clearance_mm listed_capacity_dfu atmospheric_relief_present accessible correctly_oriented approved_product connection_position_verified circuit_relief_verified')
    ref=text(data,'source_id');kind=data.get('arrangement')
    if kind not in ('wet','circuit','aav'):raise ValueError('Select wet, circuit or aav')
    fixtures=rows(data,'fixtures');unique(fixtures);load=0;floors=set();checks=[]
    allowed=data.get('allowed_fixture_types')
    if not isinstance(allowed,list) or not allowed or not all(isinstance(s,str) and s for s in allowed):raise ValueError('Explicit reviewed allowed_fixture_types are required')
    for f in fixtures:
        fields(f,'id source_id fixture_type floor dfu');identity=text(f,'id');source=text(f,'source_id');floors.add(text(f,'floor'));load+=num(f,'dfu',minimum=0)
        checks.append(check(identity+':fixture_applicability',f.get('fixture_type') in allowed,f.get('fixture_type'),allowed,'fixture type',source))
    maximum=num(data,'maximum_fixtures',positive=True)
    if int(maximum)!=maximum:raise ValueError('maximum_fixtures must be an integer')
    capacity=num(data,'maximum_dfu',positive=True);selected=num(data,'selected_vent_nominal_mm',positive=True);required=num(data,'required_vent_nominal_mm',positive=True)
    checks += [check('fixture_count_limit',len(fixtures)<=maximum,len(fixtures),maximum,'count',ref),check('DFU_capacity',load<=capacity,load,capacity,'DFU',ref),
        check('reviewed_vent_nominal_minimum',selected>=required,selected,required,'nominal mm',ref),
        check('connection_geometry_reviewed',flag(data,'connection_position_verified'),data['connection_position_verified'],True,'-',ref)]
    if kind in ('wet','aav'):checks.append(check('same_floor',len(floors)==1,sorted(floors),'one floor','floor',ref))
    if kind=='circuit':checks.append(check('relief_vent_configuration_reviewed',flag(data,'circuit_relief_verified'),data['circuit_relief_verified'],True,'-',ref))
    if kind=='aav':
        minimum=num(data,'minimum_clearance_mm',minimum=0);actual=num(data,'actual_clearance_mm',minimum=0);listed=num(data,'listed_capacity_dfu',positive=True)
        checks += [check('AAV_listed_capacity',load<=listed,load,listed,'DFU',ref),check('AAV_clearance',actual>=minimum,actual,minimum,'mm',ref)]
        for key in ('atmospheric_relief_present','accessible','correctly_oriented','approved_product'):
            checks.append(check(key,flag(data,key),data[key],True,'-',ref))
    return result({'total_dfu':load,'fixture_count':len(fixtures)}, {'total_dfu':'DFU','fixture_count':'count'},checks,
        notes=['Rules and product limits are supplied explicitly from the applicable code/listing; no default IPC/SBC table is invented. Geometry flags are attributed review assertions, not a CAD inference. AAVs admit air and do not replace positive-pressure relief. Complete vent sizing, stack/branch intervals, offsets, sanitary arrangement, product testing and authority approval remain unevaluated.'])


def backwater_overflow(data):
    fields(data,'source_id downstream_design_hgl_m connection_invert_m lowest_flood_rim_m protective_device_reviewed overflow_kind upstream_water_level_m tailwater_level_m crest_m weir_width_m weir_coefficient_m05_s orifice_center_m orifice_height_m orifice_area_m2 discharge_coefficient design_inflow_lps')
    ref=text(data,'source_id');hgl=num(data,'downstream_design_hgl_m');invert=num(data,'connection_invert_m');rim=num(data,'lowest_flood_rim_m')
    if rim<=invert:raise ValueError('Flood rim must be above connection invert')
    device=flag(data,'protective_device_reviewed');risk=hgl>=invert
    checks=[check('backwater_protection_review',not risk or device,device if risk else 'not triggered','reviewed protection when HGL reaches connection','-',ref),
        check('flood_rim_above_external_HGL',rim>hgl,rim-hgl,0,'m',ref)]
    upstream=num(data,'upstream_water_level_m');tail=num(data,'tailwater_level_m');inflow=num(data,'design_inflow_lps',minimum=0);kind=data.get('overflow_kind')
    if kind=='weir':
        crest=num(data,'crest_m');width=num(data,'weir_width_m',positive=True);coef=num(data,'weir_coefficient_m05_s',positive=True)
        if tail>crest:return result({'overflow_capacity_lps':None},{'overflow_capacity_lps':'L/s'},checks,complete=False,notes=['Submerged weir not modeled; supply an appropriate authenticated tailwater rating curve.'])
        capacity=coef*width*max(0,upstream-crest)**1.5*1000
    elif kind=='orifice':
        center=num(data,'orifice_center_m');height=num(data,'orifice_height_m',positive=True);area=num(data,'orifice_area_m2',positive=True);cd=num(data,'discharge_coefficient',positive=True,maximum=1)
        if upstream<center+height/2:return result({'overflow_capacity_lps':None},{'overflow_capacity_lps':'L/s'},checks,complete=False,notes=['Partially wetted orifice is outside the full-opening model.'])
        if center-height/2<tail<center+height/2:return result({'overflow_capacity_lps':None},{'overflow_capacity_lps':'L/s'},checks,complete=False,notes=['Partially submerged tailwater requires an integrated opening model.'])
        head=max(0,upstream-max(center,tail));capacity=cd*area*math.sqrt(2*G*head)*1000
    else:raise ValueError('Overflow kind must be weir or orifice')
    checks.append(check('overflow_capacity',capacity>=inflow,capacity,inflow,'L/s',ref))
    return result({'overflow_capacity_lps':capacity,'HGL_to_connection_margin_m':invert-hgl,'flood_rim_margin_m':rim-hgl},
        {'overflow_capacity_lps':'L/s','HGL_to_connection_margin_m':'m','flood_rim_margin_m':'m'},checks,
        notes=['Static HGL/protection and idealized free weir/full-opening orifice screens only. Device review does not simulate valve closure/reliability. Sewer network surcharge, downstream obstruction, access and complete overflow routing require separate analysis.'])
