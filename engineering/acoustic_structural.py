"""Source-driven airborne sound, straight-pipe stress and relief selection."""
import math
from engineering.common import fields, num, text, rows, unique, check, result


def acoustic_prediction(data):
    fields(data,'source_id limit_dba bands sources')
    ref=text(data,'source_id'); limit=num(data,'limit_dba')
    bands=rows(data,'bands',limit=16)
    if len({num(b,'frequency_hz',positive=True) for b in bands})!=len(bands): raise ValueError('Duplicate frequency band')
    for b in bands:
        fields(b,'frequency_hz a_weight_db room_constant_m2'); num(b,'frequency_hz',positive=True)
        num(b,'a_weight_db'); num(b,'room_constant_m2',positive=True)
    sources=rows(data,'sources',limit=100); unique(sources); energy={b['frequency_hz']:0. for b in bands}; trace=[]
    for s in sources:
        fields(s,'id source_id distance_m directivity_factor condition_reference spectrum')
        text(s,'source_id'); text(s,'condition_reference')
        distance=num(s,'distance_m',positive=True); directivity=num(s,'directivity_factor',positive=True,maximum=8)
        spectrum=rows(s,'spectrum',limit=16)
        if len({num(p,'frequency_hz',positive=True) for p in spectrum})!=len(spectrum): raise ValueError('Duplicate source frequency band')
        if {v['frequency_hz'] for v in spectrum}!=set(energy): raise ValueError('Every sound source must cover every declared frequency band')
        for p in spectrum:
            fields(p,'frequency_hz sound_power_db attenuation_db'); num(p,'sound_power_db',minimum=-200,maximum=200)
            num(p,'attenuation_db',minimum=0,maximum=200)
            band=next(b for b in bands if b['frequency_hz']==p['frequency_hz'])
            transfer=directivity/(4*math.pi*distance**2)+4/band['room_constant_m2']
            lp=p['sound_power_db']+10*math.log10(transfer)-p['attenuation_db']
            energy[p['frequency_hz']]+=10**(lp/10)
            trace.append(dict(kind='source_band',id=s['id'],frequency_hz=p['frequency_hz'],receiver_sound_pressure_db=lp,source_id=s['source_id']))
    weighted=0.
    for b in bands:
        lp=10*math.log10(energy[b['frequency_hz']]); weighted+=energy[b['frequency_hz']]*10**(b['a_weight_db']/10)
        trace.append(dict(kind='combined_band',frequency_hz=b['frequency_hz'],combined_sound_pressure_db=lp,a_weighted_band_db=lp+b['a_weight_db']))
    total=10*math.log10(weighted)
    return result(dict(predicted_receiver_dba=total,acoustic_margin_db=limit-total),
        dict(predicted_receiver_dba='dBA',acoustic_margin_db='dB'),[check('airborne_receiver_level',total<=limit,total,limit,'dBA',ref)],trace,
        notes=['Incoherent sound-power spectra combined using direct plus diffuse room-field transfer, supplied room constants, attenuation and A-weight corrections. Source sound power must match the equipment, duty and spectral measurement conditions.',
            'Far-field engineering prediction; no source noise inferred from pipe velocity. Structure-borne vibration, coherent sources, near-field effects, flanking paths and transient/cavitation noise require separate evidence.'])


def pipe_stress(data):
    fields(data,'source_id internal_mm external_mm internal_gauge_kpa external_gauge_kpa length_m '
        'youngs_modulus_mpa material_alpha_per_k temperature_change_k restraint_fraction bending_moment_nm '
        'stress_intensification allowable_stress_mpa allowable_anchor_force_n')
    ref=text(data,'source_id'); ri=num(data,'internal_mm',positive=True)/2000; ro=num(data,'external_mm',positive=True)/2000
    if ro<=ri: raise ValueError('Outside diameter must exceed internal bore')
    pi=num(data,'internal_gauge_kpa',minimum=0)*1000; po=num(data,'external_gauge_kpa',minimum=0)*1000
    if po>pi: raise ValueError('External-pressure buckling is outside this straight-pipe elastic stress model')
    length=num(data,'length_m',positive=True); young=num(data,'youngs_modulus_mpa',positive=True)*1e6
    alpha=num(data,'material_alpha_per_k',minimum=0); delta=num(data,'temperature_change_k')
    restrained=num(data,'restraint_fraction',minimum=0,maximum=1); moment=num(data,'bending_moment_nm',minimum=0)
    sif=num(data,'stress_intensification',minimum=1)
    allow=num(data,'allowable_stress_mpa',positive=True); force_limit=num(data,'allowable_anchor_force_n',minimum=0)
    area=math.pi*(ro**2-ri**2); inertia=math.pi*(ro**4-ri**4)/4
    a=(pi*ri**2-po*ro**2)/(ro**2-ri**2); b=(pi-po)*ri**2*ro**2/(ro**2-ri**2)
    thermal=-young*alpha*delta*restrained; force=abs(thermal*area); peak=0.; trace=[]
    for radius in (ri,ro):
        hoop=a+b/radius**2; radial=a-b/radius**2
        for sign in (-1,1):
            axial=a+thermal+sign*sif*moment*radius/inertia
            vm=math.sqrt(((hoop-radial)**2+(radial-axial)**2+(axial-hoop)**2)/2)/1e6
            peak=max(peak,vm)
            trace.append(dict(radius_mm=radius*1000,bending_sign=sign,hoop_mpa=hoop/1e6,radial_mpa=radial/1e6,axial_mpa=axial/1e6,von_mises_mpa=vm))
    return result(dict(maximum_von_mises_mpa=peak,thermal_axial_stress_mpa=thermal/1e6,thermal_anchor_force_n=force,
        free_expansion_mm=alpha*delta*length*1000,stress_margin_mpa=allow-peak),
        dict(maximum_von_mises_mpa='MPa',thermal_axial_stress_mpa='MPa',thermal_anchor_force_n='N',free_expansion_mm='mm',stress_margin_mpa='MPa'),
        [check('elastic_equivalent_stress',peak<=allow,peak,allow,'MPa',ref),check('thermal_anchor_reaction',force<=force_limit,force,force_limit,'N',ref)],trace,
        notes=['Lamé elastic straight-cylinder pressure stresses with closed-end axial pressure stress, supplied linear axial restraint, longitudinal bending and a supplied stress intensification factor. Radial stress included in von Mises comparison.',
            'Homogeneous linear-elastic straight pipe only. Supplied allowable is not derived from ASME B31. No network flexibility, elbow/local support stress, fatigue, creep, buckling, pressure-code compliance or certified stress report.'])


def relief_selection(data):
    fields(data,'source_id service rating_basis normal_gauge_kpa maximum_permitted_gauge_kpa required_capacity_kw '
        'maximum_temperature_c minimum_set_margin_kpa required_listing catalogue')
    ref=text(data,'source_id'); service=text(data,'service'); basis=text(data,'rating_basis'); listing=text(data,'required_listing')
    normal=num(data,'normal_gauge_kpa',minimum=0); maximum=num(data,'maximum_permitted_gauge_kpa',positive=True)
    capacity=num(data,'required_capacity_kw',positive=True); temp=num(data,'maximum_temperature_c')
    margin=num(data,'minimum_set_margin_kpa',minimum=0)
    if normal>=maximum: raise ValueError('Normal pressure must be below maximum permitted pressure')
    catalogue=rows(data,'catalogue',limit=500); unique(catalogue,'model'); trace=[]; eligible=[]
    for row in catalogue:
        fields(row,'model source_id service rating_basis set_gauge_kpa certified_capacity_kw rating_temperature_c listing evidence_reference')
        model=text(row,'model'); source=text(row,'source_id'); text(row,'evidence_reference')
        setpoint=num(row,'set_gauge_kpa',positive=True); rating=num(row,'certified_capacity_kw',positive=True); ratedtemp=num(row,'rating_temperature_c')
        reasons=[]
        if text(row,'service')!=service: reasons.append('Service mismatch')
        if text(row,'rating_basis')!=basis: reasons.append('Capacity rating basis mismatch; temperature and pressure ratings are not interchangeable')
        if text(row,'listing')!=listing: reasons.append('Required listing evidence does not match')
        if setpoint>maximum: reasons.append('Set pressure exceeds permitted pressure')
        if setpoint<normal+margin: reasons.append('Set pressure lacks operating margin')
        if rating<capacity: reasons.append('Certified capacity below required input')
        if ratedtemp<temp: reasons.append('Temperature rating insufficient')
        if not reasons: eligible.append(model)
        trace.append(dict(model=model,source_id=source,eligible=not reasons,rejection_reasons=reasons))
    return result(dict(eligible_models=eligible,eligible_count=len(eligible)),dict(eligible_models='model IDs',eligible_count='count'),
        [check('compatible_supplied_relief_rating',bool(eligible),len(eligible),1,'models',ref)],trace,
        notes=['Filters supplied manufacturer/listing evidence at the declared service, set pressure, capacity basis and temperature. No manufacturer certification or capacity value is generated by the engine.',
            'Discharge piping, inlet pressure loss, backpressure, temperature sensing, accumulation, installation, maintenance and authority acceptance remain unevaluated.'])
