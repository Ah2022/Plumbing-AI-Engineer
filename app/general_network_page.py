"""Native general-network editing, scenario review and governed saving."""
from copy import deepcopy
import json
import math
from pathlib import Path
import pandas as pd
import streamlit as st
from app.db_helpers import save_calculation,next_calc_id
from models import CalculationResult
from solvers.graph import normalize_graph,keys
from solvers.epanet_input import build_input
from solvers.service import solve_network,run_scenarios,compare_tree,configured_library,fingerprint

ROOT=Path(__file__).resolve().parents[1]
EXAMPLES={'Looped water network':'pressure_loop','Pressure-dependent demand':'pressure_pda','24-hour pumps, tank and valve':'pressure_eps'}
FIELDS={
 'junction':'id kind elevation_m demand_lps fire_demand_lps demand_pattern required_pressure_m demand_reference reference',
 'source':'id kind elevation_m head_m reference',
 'tank':'id kind elevation_m initial_level_m min_level_m max_level_m diameter_m min_volume_m3 reference',
 'pipe':'id kind from_node to_node length_m internal_mm roughness roughness_unit minor_loss_k status reference',
 'pump':'id kind from_node to_node curve_id speed status reference',
 'valve':'id kind from_node to_node internal_mm valve_type setting setting_unit minor_loss_k status reference'}


def edit_group(items,kind,key):
    frame=pd.DataFrame([r for r in items if r['kind']==kind],columns=FIELDS[kind].split())
    labels={name:name.replace('_',' ').capitalize() for name in frame.columns}
    labels.update(internal_mm='Actual internal bore (mm)',head_m='Absolute hydraulic head (m)',
        required_pressure_m='Required pressure head (m)',demand_lps='Base demand (L/s)',id='ID',kind=None)
    edited=st.data_editor(frame,num_rows='dynamic',disabled=['kind'],column_config=labels,key=key,width='stretch',
        alt=kind.capitalize()+' engineering input table with SI dimensions and source references')
    rows=[]
    for row in edited.to_dict('records'):
        clean={k:v for k,v in row.items() if v is not None and not (isinstance(v,float) and math.isnan(v)) and v!=''}
        if not clean.get('id'):continue
        clean['kind']=kind;rows.append(clean)
    return rows


def render_diagram(model):
    lines=['digraph network { rankdir=LR;']
    for n in model['nodes']:
        shape={'source':'box','tank':'cylinder','junction':'ellipse'}[n['kind']]
        lines.append(json.dumps(n['id'])+' [shape='+shape+', label='+json.dumps(n['id']+' - '+n['kind'])+'];')
    for e in model['links']:
        lines.append(json.dumps(e['from_node'])+' -> '+json.dumps(e['to_node'])+' [label='+json.dumps(e['id']+' - '+e['kind'])+'];')
    st.graphviz_chart('\n'.join(lines+['}']),width='stretch',alt='General pressure graph showing sources, junctions, tanks and directed pipe/pump/valve references; flow may reverse in simulation')


def save_general_result(conn,pid,network_id,result):
    if not isinstance(network_id,str) or not network_id.strip():raise ValueError('General network review ID is required')
    code=conn.execute('SELECT code_id FROM projects WHERE project_id=?',(pid,)).fetchone()[0]
    if result['normalized_model'].get('code_id')!=code:raise ValueError('Solver model code must match the active project')
    if result['review_status']!='REVIEW_REQUIRED' or result['code_compliance_status']!='NOT_EVALUATED':raise ValueError('General solver results cannot bypass engineering/code review')
    calc=CalculationResult(next_calc_id(conn,pid,'general_network_check'),'general_network_check',
        'EPANET2.2 hydraulic solution of specified pressure network; code compliance is not evaluated',
        {'network':result['normalized_model']},dict(result,coverage_status='PARTIAL'),
        result.get('minimum_pressure_margin_m'),'m pressure margin',status=result['technical_status'] if result['complete'] else 'MISSING_DATA',
        reference='EPANET2.2; explicit model/source references; project code checks pending',notes='; '.join(result['limitations']))
    save_calculation(conn,pid,calc,target_type='network',target_id=network_id)
    return calc.calc_id


def page_general_network(conn,pid,code,revision):
    st.subheader('General pressure-network solver')
    st.warning('Hydraulic results require engineering review. Code compliance is not evaluated by this solver. Fire demand is a hydraulic load case only.')
    lib=configured_library()
    st.caption('EPANET 2.2 backend: '+('configured' if lib and lib.is_file() else 'unavailable — configure PLUMBING_EPANET_LIBRARY on the server'))
    example=st.selectbox('General-network example',list(EXAMPLES))
    scope=f'general_{pid}_{code}_{revision}_{EXAMPLES[example]}'
    template=json.loads((ROOT/'examples'/(EXAMPLES[example]+'.json')).read_text(encoding='utf-8'));template['code_id']=code
    upload=st.file_uploader('Upload general pressure-network JSON',type=['json'],max_upload_size=10,key=scope+'_upload')
    if upload:
        try:template=json.loads(upload.getvalue().decode('utf-8-sig'))
        except (ValueError,UnicodeError) as error:st.error(str(error));return
    source_hash=fingerprint(template);key=scope+'_'+source_hash[:12]
    mode=st.radio('General network input method',['Editable graph tables','Mapped graph JSON'],horizontal=True,key=key+'_mode')
    model=deepcopy(template)
    try:
        # A valid source must exist before table editors can infer typed columns.
        model,_=normalize_graph(model)
        if mode=='Mapped graph JSON':
            with st.expander('Advanced mapped graph JSON',expanded=True):
                raw=st.text_area('General mapped network JSON',json.dumps(model,indent=2),height=320,key=key+'_json')
            model=json.loads(raw)
        else:
            with st.expander('Edit junctions, sources and tanks'):
                edited=[]
                for kind in ('junction','source','tank'):
                    st.caption(kind.capitalize()+' inputs');edited+=edit_group(model['nodes'],kind,key+'_'+kind)
                model['nodes']=edited
            with st.expander('Edit pipes, pumps and valves'):
                edited=[]
                for kind in ('pipe','pump','valve'):
                    st.caption(kind.capitalize()+' inputs');edited+=edit_group(model['links'],kind,key+'_'+kind)
                model['links']=edited
            with st.expander('Simulation and demand settings'):
                sim=model['simulation'];dm=model['demand_model']
                sim['duration_s']=int(st.number_input('Simulation duration (hours)',min_value=0.,max_value=168.,value=sim['duration_s']/3600,step=1.,key=key+'_duration')*3600)
                sim['hydraulic_step_s']=int(st.number_input('Hydraulic timestep (minutes)',min_value=1,max_value=1440,value=max(1,sim['hydraulic_step_s']//60),key=key+'_hydstep')*60)
                sim['pattern_step_s']=int(st.number_input('Pattern timestep (minutes)',min_value=1,max_value=1440,value=max(1,sim['pattern_step_s']//60),key=key+'_patstep')*60)
                dm_type=st.selectbox('Demand delivery model',['DDA','PDA'],index=['DDA','PDA'].index(dm['type']),key=key+'_demand')
                model['demand_model']={'type':dm_type,'reference':dm['reference']}
                if dm_type=='PDA':
                    for field,label,default in [('minimum_pressure_m','PDA zero-delivery pressure (m)',0.),('required_pressure_m','PDA full-delivery pressure (m)',20.),('exponent','PDA pressure exponent',.5)]:
                        model['demand_model'][field]=st.number_input(label,min_value=0.,value=float(dm.get(field,default)),key=key+'_'+field)
            with st.expander('Advanced equipment definitions'):
                st.caption('Pump curves use flow L/s and head m. Patterns are dimensionless. Controls use elapsed seconds or tank-level/junction-pressure metres. Scenario closures hold links out of service and disable their controls.')
                definitions=st.text_area('Curves, patterns, controls and scenarios (JSON)',json.dumps({k:model[k] for k in ('curves','patterns','controls','scenarios')},indent=2),height=260,key=key+'_equipment')
                data=json.loads(definitions);keys(data,'curves patterns controls scenarios','Equipment definitions');model.update(data)
        normalized,topo=normalize_graph(model)
        if normalized.get('code_id')!=code:raise ValueError('General model code_id must match the active project')
    except (ValueError,TypeError,KeyError) as error:
        st.error('Model needs correction: '+str(error));return
    token=fingerprint(normalized)
    st.caption(f"{len(normalized['nodes'])} nodes · {len(normalized['links'])} links · {'loops detected: EPANET required' if topo['has_loops'] else 'general graph: EPANET backend'}")
    render_diagram(normalized)
    st.download_button('Download normalized graph JSON',json.dumps(normalized,indent=2),file_name='pressure-network.json',mime='application/json')
    st.download_button('Download EPANET input',build_input(normalized),file_name='pressure-network.inp',mime='text/plain')
    network_id=st.text_input('General network review ID',value='GENERAL-1',key=key+'_networkid')
    if st.button('Run general hydraulic simulation',key=key+'_run'):
        with st.spinner('Solving the specified pressure network…'):
            st.session_state[scope+'_result']={'input':token,'result':solve_network(normalized)}
    if normalized['scenarios'] and st.button('Run declared scenario analysis',key=key+'_scenarios'):
        with st.spinner('Solving each declared scenario…'):
            st.session_state[scope+'_scenarios']={'input':token,'result':run_scenarios(normalized)}
    stored=st.session_state.get(scope+'_result')
    if stored and stored['input']!=token:st.info('Inputs changed. Rerun before reviewing or saving results.');stored=None
    if stored:
        result=stored['result'];st.metric('Hydraulic solver status',result['solver_status'])
        st.metric('Specified pressure/demand criteria',result['technical_status'])
        st.caption('Engineering review: REVIEW_REQUIRED · Code compliance: NOT_EVALUATED')
        for diagnostic in result['diagnostics']:st.warning(diagnostic['message']+' '+diagnostic['action'])
        if result['snapshots']:
            snapshot=st.selectbox('Hydraulic event time (seconds)',[s['time_s'] for s in result['snapshots']],key=scope+'_time')
            step=next(s for s in result['snapshots'] if s['time_s']==snapshot)
            st.dataframe(step['nodes'],width='stretch',alt='Node pressures, requested and delivered demands, deficits and tank levels at the selected time')
            st.dataframe(step['links'],width='stretch',alt='Link flow, status, velocity and signed hydraulic head drop at the selected time')
        if result['complete']:
            st.metric('Minimum pressure margin (m)',round(result['minimum_pressure_margin_m'],4))
            st.metric('Maximum unmet demand (L/s)',round(result['maximum_demand_deficit_lps'],4))
        if st.button('Save general-network review',key=scope+'_save'):
            try:st.success('Review saved: '+save_general_result(conn,pid,network_id,result))
            except ValueError as error:st.error(str(error))
        st.download_button('Download hydraulic findings',json.dumps(result,indent=2),file_name='hydraulic-findings.json',mime='application/json')
    scenarios=st.session_state.get(scope+'_scenarios')
    if scenarios and scenarios['input']==token:
        st.subheader('Scenario findings')
        st.dataframe([dict(scenario=r['scenario']['label'],solver=r['result']['solver_status'],technical=r['result']['technical_status'],minimum_pressure_margin_m=r['result'].get('minimum_pressure_margin_m'),maximum_deficit_lps=r['result'].get('maximum_demand_deficit_lps')) for r in scenarios['result']['scenarios']],width='stretch',alt='Each declared scenario, hydraulic completion, pressure margin and unmet demand')
        st.download_button('Download scenario findings',json.dumps(scenarios['result'],indent=2),file_name='scenario-findings.json',mime='application/json')
    with st.expander('Compare the existing tree evaluator'):
        st.caption('Run the five frozen Phase 1 A water envelopes through both boundaries. The tree numbers remain unchanged; documented EPANET conventions explain small head differences.')
        if st.button('Compare five equivalent tree cases',key=scope+'_compare'):
            comparisons=[]
            for folder in sorted((ROOT/'validation/phase1a/projects').iterdir()):
                model=json.loads((folder/'input.json').read_text(encoding='utf-8'))['water_model']
                comparisons.append(dict(project=folder.name,result=compare_tree(model)))
            st.session_state[scope+'_comparison']=comparisons
        comparisons=st.session_state.get(scope+'_comparison')
        if comparisons:
            st.dataframe([dict(project=c['project'],**row) for c in comparisons for row in c['result']['comparison']],width='stretch',alt='Equivalent tree pressures, EPANET pressures and residuals after published convention reconciliation')
            st.download_button('Download tree/backend comparison',json.dumps(comparisons,indent=2),file_name='tree-epanet-comparison.json',mime='application/json')
