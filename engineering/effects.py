"""Bounded surge, acoustic-risk and thermal expansion engineering screens."""
import math
from engineering.common import fields,num,text,check,result,G


def noise_screen(data):
    fields(data,'source_id flow_lps internal_mm reviewed_velocity_limit_m_s measured_noise_db acoustic_limit_db measurement_metric limit_metric operating_condition_reference')
    ref=text(data,'source_id');flow=num(data,'flow_lps',minimum=0);d=num(data,'internal_mm',positive=True)/1000;limit=num(data,'reviewed_velocity_limit_m_s',positive=True)
    velocity=flow/1000/(math.pi*d*d/4);checks=[check('velocity_acoustic_risk_screen',velocity<=limit,velocity,limit,'m/s',ref)]
    values={'velocity_m_s':velocity};units={'velocity_m_s':'m/s'}
    if data.get('measured_noise_db') is not None or data.get('acoustic_limit_db') is not None:
        if text(data,'measurement_metric')!=text(data,'limit_metric'):raise ValueError('Acoustic metrics differ; no valid dB limit comparison can be made')
        text(data,'operating_condition_reference')
        noise=num(data,'measured_noise_db');acoustic=num(data,'acoustic_limit_db');checks.append(check('measured_acoustic_limit',noise<=acoustic,noise,acoustic,'dB',ref));values['measured_noise_db']=noise;units['measured_noise_db']='dB, supplied measurement metric'
    return result(values,units,checks,notes=['Velocity is a risk screen, not a dBA sound prediction. Any measured/noise-limit comparison must use the same weighting, location and operating condition. Cavitation, fittings, support vibration and room acoustics are not modeled.'])


def water_hammer(data):
    fields(data,'source_id water_density_kg_m3 wave_speed_m_s pipe_length_m initial_velocity_m_s final_velocity_m_s closure_time_s operating_gauge_kpa allowable_gauge_kpa atmospheric_kpa vapour_pressure_kpa closure_model')
    ref=text(data,'source_id');rho=num(data,'water_density_kg_m3',positive=True);speed=num(data,'wave_speed_m_s',positive=True);length=num(data,'pipe_length_m',positive=True)
    v0=num(data,'initial_velocity_m_s');v1=num(data,'final_velocity_m_s');time=num(data,'closure_time_s',positive=True)
    operating=num(data,'operating_gauge_kpa');allowable=num(data,'allowable_gauge_kpa',positive=True);atmosphere=num(data,'atmospheric_kpa',positive=True);vapour=num(data,'vapour_pressure_kpa',minimum=0)
    if data.get('closure_model')!='linear_velocity':raise ValueError('Only the explicit linear_velocity single-line closure screen is supported')
    if operating+atmosphere<=vapour:raise ValueError('Initial absolute pressure must exceed supplied vapour pressure')
    critical=2*length/speed;rapid=rho*speed*abs(v0-v1)/1000
    surge=rapid*min(1,critical/time);maximum=operating+surge;minimum_absolute=operating+atmosphere-surge
    return result({'critical_closure_time_s':critical,'rapid_closure_surge_kpa':rapid,'screened_surge_kpa':surge,
        'maximum_gauge_kpa':maximum,'minimum_absolute_kpa':minimum_absolute},
        {'critical_closure_time_s':'s','rapid_closure_surge_kpa':'kPa','screened_surge_kpa':'kPa','maximum_gauge_kpa':'kPa gauge','minimum_absolute_kpa':'kPa absolute'},
        [check('pressure_rating_screen',maximum<=allowable,maximum,allowable,'kPa gauge',ref),check('vapour_pressure_screen',minimum_absolute>vapour,minimum_absolute,vapour,'kPa absolute',ref)],
        notes=['Joukowsky rapid-closure envelope and simple2L/(a*t) slow linear-velocity factor. The symmetric low-pressure envelope flags cavitation risk; it does not simulate column separation. Wave speed must be reviewed for pipe/fluid/restraint. No method-of-characteristics network transient, air vessel or arrestor sizing is claimed.'])


def thermal_expansion(data):
    fields(data,'source_id cold_water_volume_l cold_density_kg_m3 hot_density_kg_m3 pipe_length_m material_alpha_per_k temperature_rise_k precharge_gauge_kpa cold_fill_gauge_kpa maximum_gauge_kpa atmospheric_kpa polytropic_exponent selected_vessel_l')
    ref=text(data,'source_id');volume=num(data,'cold_water_volume_l',minimum=0);cold=num(data,'cold_density_kg_m3',positive=True);hot=num(data,'hot_density_kg_m3',positive=True)
    length=num(data,'pipe_length_m',minimum=0);alpha=num(data,'material_alpha_per_k',minimum=0);dt=num(data,'temperature_rise_k',minimum=0)
    pre=num(data,'precharge_gauge_kpa',minimum=0);fill=num(data,'cold_fill_gauge_kpa',minimum=0);maximum=num(data,'maximum_gauge_kpa',positive=True);atm=num(data,'atmospheric_kpa',positive=True)
    exponent=num(data,'polytropic_exponent',minimum=1,maximum=1.67);selected=num(data,'selected_vessel_l',minimum=0)
    if not pre<=fill<maximum:raise ValueError('Require precharge <= cold fill < maximum permitted gauge pressure')
    expansion=max(0,volume*(cold/hot-1));pre+=atm;fill+=atm;maximum+=atm
    acceptance=(pre/fill)**(1/exponent)-(pre/maximum)**(1/exponent)
    required=expansion/acceptance
    return result({'water_expansion_l':expansion,'free_pipe_elongation_mm':alpha*length*dt*1000,
        'ideal_vessel_acceptance_fraction':acceptance,'minimum_ideal_vessel_l':required},
        {'water_expansion_l':'L','free_pipe_elongation_mm':'mm','ideal_vessel_acceptance_fraction':'-','minimum_ideal_vessel_l':'L'},
        [check('ideal_vessel_volume_screen',selected>=required,selected,required,'L',ref)],
        notes=['Density-based water expansion, free linear pipe expansion and ideal polytropic gas acceptance using absolute pressures. Cold/hot densities and material alpha must match the reviewed temperatures/material. Usable manufacturer acceptance, membrane limits, relief-valve margin, glycol corrections, supports and restrained stress/flexibility are not selected or certified.'])
