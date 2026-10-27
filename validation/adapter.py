"""Production adapter only. Expected values come exclusively from frozen files."""
import importlib
import json
import math
from pathlib import Path
from database.db import init_db

DATA=Path(__file__).parent/'phase1a'
UNEVALUATED_CHECKS=[
    'fixture diversity and WSFU-to-flow applicability','minimum-pressure survey and pressure zones',
    'backflow and maximum static pressure','hot-water recirculation heat loss, balancing, scald and hygiene controls',
    'pump curve/NPSH and tank operation','drainage vent/trap/cleanout/offset arrangement',
    'storm secondary drainage and local rainfall adoption','CAD/IFC/Revit extraction completeness',
    'all licensed code-table values and local amendments']


def load(name):
    return json.loads((DATA/name).read_text(encoding='utf-8'))


def reference_connection():
    conn=init_db(':memory:')
    for code in ('REFERENCE','IPC'):
        conn.execute('INSERT INTO codes(code_id,code_name) VALUES (?,?)',(code,'Fictional validation fixture; not authenticated code data'))
    for table in load('lookup-fixtures.json'):
        tid=conn.execute("INSERT INTO design_tables(code_id,domain,table_name,reference,status) VALUES (?,?,?,?,'POPULATED')",(table['code'],table['domain'],table['name'],table['reference'])).lastrowid
        for i,row in enumerate(table['rows']):
            for key,value in row.items():
                conn.execute("INSERT INTO design_table_values(table_id,row_key,col_key,value_num,value_text,confidence) VALUES (?,?,?,?,?,'CONFIRMED')",(tid,str(i),key,value if isinstance(value,(int,float)) else None,value if isinstance(value,str) else None))
    conn.commit();return conn


def run_method(case,conn):
    # A frozen, explicit whitelist. No evaluation of arbitrary module names.
    allowed={row['entrypoint'] for row in load('method-cases.json')}
    entry=case['entrypoint']
    if entry not in allowed or not entry.startswith('calculations.'):
        raise ValueError('Unknown reference calculation entrypoint')
    mod,name=entry.rsplit('.',1);fn=getattr(importlib.import_module(mod),name)
    args=dict(case['inputs'])
    if case.get('special')=='hot_storage':
        from models import CalculationResult
        # Fixed independent prerequisite, not a call to the demand implementation.
        args['hot_water_demand_result']=CalculationResult('REFERENCE-DEMAND','hot_water_demand','Fixed prerequisite',{}, {},100,'GPH',selected_value=60,status='CALCULATED_NOT_APPROVED')
    if case.get('connection'):args['conn']=conn
    if not case.get('no_calc_id'):args['calc_id']='REFERENCE-'+case['id']
    result=fn(**args)
    if isinstance(result,dict):value=result[case['field']];status=result.get('technical_status')
    else:value=result.result_value;status=result.status
    expected=case.get('expected_text',case['expected'])
    matches=(value==expected if isinstance(expected,str) else math.isclose(value,expected,rel_tol=0,abs_tol=case['absolute_tolerance']))
    if case.get('status'): matches=matches and status==case['status']
    if not isinstance(result,dict):matches=matches and result.result_unit.startswith(case['unit'])
    if 'required' in case:matches=matches and math.isclose(result.required_value,case['required'],rel_tol=0,abs_tol=case['absolute_tolerance'])
    return dict(case=case['id'],expected=expected,actual=value,software_status='PASS' if matches else 'FAIL',technical_status=status,
                evidence_class=case['evidence_class'],engineering_status='REVIEW_REQUIRED')


def run_project(project,expected,conn):
    from calculations.network import analyze_water_network,analyze_drainage_network
    from calculations.hot_water import heater_capacity
    from calculations.tanks import size_domestic_water_tank
    from calculations.pumps import select_pump_duty
    from calculations.hydraulics import rational_method_peak_flow
    actual=analyze_water_network(project['water_model'])
    differences=[]
    def same(label,a,b,tol=1e-8):
        okay=math.isclose(a,b,rel_tol=0,abs_tol=tol) if isinstance(b,(int,float)) else a==b
        if not okay:differences.append(dict(field=label,expected=b,actual=a,explanation='UNEXPLAINED_ENGINE_DISCREPANCY'))
    same('water.pipe_ids',sorted(r['pipe_id'] for r in actual['pipes']),sorted(expected['pipes']))
    same('water.terminal_ids',sorted(r['terminal_id'] for r in actual['terminals']),sorted(expected['terminals']))
    for row in actual['pipes']:
        for key,value in expected['pipes'][row['pipe_id']].items():same(row['pipe_id']+'.'+key,row[key],value)
    for row in actual['terminals']:
        for key,value in expected['terminals'][row['terminal_id']].items():same(row['terminal_id']+'.'+key,row[key],value)
    for key in ('governing_terminal','minimum_pressure_margin_m','technical_status','review_status'):same(key,actual[key],expected[key])
    drainage=analyze_drainage_network(conn,'REFERENCE',project['drainage_model'])
    de=expected['drainage']
    same('drainage.pipe_ids',sorted(r['pipe_id'] for r in drainage['pipes']),sorted(de['required_sizes_mm']))
    for key in ('total_drainage_dfu','technical_status','coverage_status'):same('drainage.'+key,drainage[key],de[key])
    for pipe in drainage['pipes']:
        for field,lookup in [('required_nominal_mm','required_sizes_mm'),('actual_slope_pct','actual_slopes_pct')]:same('drainage.'+pipe['pipe_id']+'.'+field,pipe.get(field),de[lookup][pipe['pipe_id']])
    s=project['systems'];h=s['pump_head_components_m']
    values=dict(heater_kw=heater_capacity(s['heater_mass_flow_kg_s'],s['cold_c'],s['hot_c'],'REF-H').result_value,
        domestic_storage_m3=size_domestic_water_tank(s['average_demand_lps'],s['storage_hours'],'REF-T',s['storage_margin_pct']).result_value,
        pump_power_kw=select_pump_duty(s['pump_flow_lps'],*h,s['pump_efficiency'],'REF-P').result_value,
        storm_flow_lps=rational_method_peak_flow(s['runoff_coefficient'],s['rainfall_mm_hr'],s['roof_area_m2'],'REF-S').result_value)
    for key,value in values.items():same(key,value,expected[key],.00051 if key=='domestic_storage_m3' else .000051)
    warnings=['CODE_EDITION_AND_TABLES_UNVERIFIED','MANUFACTURER_CATALOGUE_UNVERIFIED','INDEPENDENT_ENGINEER_REVIEW_PENDING']
    if drainage['coverage_status']=='PARTIAL':warnings.append('DRAINAGE_PARTIAL_COVERAGE')
    same('expected_warnings',warnings,expected['expected_warnings'])
    same('unevaluated_checks',UNEVALUATED_CHECKS,expected['unevaluated_checks'])
    return dict(project_id=project['project_id'],software_status='FAIL' if differences else 'PASS',
                differences=differences,water=actual,drainage=drainage,system_results=values,warnings=warnings,
                unevaluated_checks=list(UNEVALUATED_CHECKS),
                engineering_status='REVIEW_REQUIRED')
