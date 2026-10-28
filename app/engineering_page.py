"""Source-first module workspace; stale/unvalidated implementations are not exposed."""
from copy import deepcopy
import json,math
from pathlib import Path
import pandas as pd
import streamlit as st
from engineering.registry import exposure_status,ROOT
from engineering.service import run_module,validate_envelope,digest
from app.db_helpers import save_calculation,next_calc_id
from models import CalculationResult
from compliance.governance import get_basis


def label(key):
    units={'_m_per_lps2':'m/(L/s)²','_kg_m3':'kg/m³','_j_kgk':'J/(kg·K)','_mm_day':'mm/day','_w_m':'W/m','_per_k':'1/K',
        '_m05_s':'m^0.5/s','_m_s':'m/s','_lps':'L/s','_kpa':'kPa','_m3':'m³','_m2':'m²','_mm':'mm','_pa':'Pa','_pct':'%',
        '_db':'dB','_c':'°C','_k':'K','_s':'s','_l':'L','_m':'m'}
    for ending,unit in units.items():
        if key.endswith(ending):return key[:-len(ending)].replace('_',' ').capitalize()+' ('+unit+')'
    return key.replace('_',' ').capitalize()


def clean(value):
    if isinstance(value,float) and math.isnan(value):return None
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if v is not None and not (isinstance(v,float) and math.isnan(v))}
    if isinstance(value,list):return [clean(v) for v in value]
    return value


def edit_data(data,key):
    result={}
    for name,value in data.items():
        widget=key+'_'+name
        if isinstance(value,bool):result[name]=st.checkbox(label(name),value=value,key=widget)
        elif isinstance(value,(int,float)):
            result[name]=st.number_input(label(name),value=float(value),key=widget,format='%.8g')
        elif isinstance(value,str):result[name]=st.text_input(label(name),value=value,key=widget)
        elif isinstance(value,dict):
            with st.expander(label(name)):
                result[name]=edit_data(value,widget)
        elif isinstance(value,list) and value and all(isinstance(row,dict) and all(not isinstance(v,(dict,list)) for v in row.values()) for row in value):
            st.caption(label(name))
            frame=st.data_editor(pd.DataFrame(value),num_rows='dynamic',column_config={k:label(k) for row in value for k in row},
                key=widget,width='stretch',alt=label(name)+' editable engineering source inputs')
            result[name]=[clean(row) for row in frame.to_dict('records') if any(v is not None and not (isinstance(v,float) and math.isnan(v)) for v in row.values())]
        else:
            with st.expander(label(name)+' — structured data'):
                result[name]=json.loads(st.text_area(label(name)+' (JSON)',json.dumps(value,indent=2),height=220,key=widget))
    return result


def _open_pressure():
    st.session_state['navigation']='Network Review'
    st.session_state['network_kind']='General pressure network'


def save_module_result(conn,pid,record_id,actor,report):
    if not isinstance(record_id,str) or not record_id.strip() or not isinstance(actor,str) or not actor.strip():raise ValueError('Calculation ID and recording reviewer are required')
    package=validate_envelope(report['input_package']);project=conn.execute('SELECT code_id,code_edition FROM projects WHERE project_id=?',(pid,)).fetchone()
    if package['code_id']!=project['code_id'] or project['code_edition'] and package['code_edition']!=project['code_edition']:raise ValueError('Input code/edition must match the active project basis')
    if report['input_sha256']!=digest(package) or report['review_status']!='REVIEW_REQUIRED' or report['code_compliance_status']!='NOT_EVALUATED':raise ValueError('Engineering report evidence/review contract is invalid')
    value=next((v for v in report['values'].values() if isinstance(v,(int,float)) and not isinstance(v,bool)),None)
    unit=next((report['units'][k] for k,v in report['values'].items() if isinstance(v,(int,float)) and not isinstance(v,bool)),None)
    calc=CalculationResult(next_calc_id(conn,pid,'engineering_module'),'engineering_module',report['scope'],
        {'engineering_package':package,'recorded_by':actor,'record_id':record_id},report,value,unit,
        status=report['technical_status'],reference='; '.join(s['document']+' / '+s['revision']+' / '+s['locator'] for s in package['sources']),
        notes='REVIEW_REQUIRED; code compliance NOT_EVALUATED; '+ '; '.join(report['not_evaluated']))
    save_calculation(conn,pid,calc,target_type='engineering_module',target_id=report['module']+':'+record_id)
    return calc.calc_id


def page_engineering_modules():
    st.header('Plumbing engineering modules')
    pid=st.session_state.get('project_id')
    if not pid:st.info('Create or open a project first.');return
    conn=st.session_state.conn;project=conn.execute('SELECT code_id,code_edition FROM projects WHERE project_id=?',(pid,)).fetchone()
    modules=exposure_status();lookup={m['id']:m for m in modules}
    with st.expander('Module scope and availability register'):
        st.dataframe([{'Priority':m['priority'],'Module':m['title'],'Available':m['available'],
            'Validation':'Software reference-tested; engineering review pending' if m['available'] else 'Matching evidence missing or stale'} for m in modules],
            width='stretch',alt='Prioritized engineering modules and matching software-validation availability')
        st.download_button('Download module scope register',json.dumps(modules,indent=2),file_name='engineering-module-scopes.json',mime='application/json')
    chosen=st.selectbox('Engineering module',list(lookup),format_func=lambda k:f"{lookup[k]['priority']}. {lookup[k]['title']}")
    metadata=lookup[chosen]
    st.subheader(metadata['title'])
    st.write('Calculation scope: '+metadata['scope'])
    st.caption('Validation: software reference checks passed; independent engineering acceptance pending.' if metadata['available']
        else 'Validation: matching reference evidence is missing or stale; calculation controls are disabled.')
    st.warning('Engineering review required. Code compliance is NOT_EVALUATED. Supplied source-review assertions do not approve this calculation or the code basis.')
    st.write('Required source data: '+'; '.join(metadata['required_source_data']))
    st.write('Unevaluated scope: '+'; '.join(metadata['not_evaluated']))
    for i,url in enumerate(metadata['method_references']):st.link_button('Method / code-review reference '+str(i+1),url)
    if not metadata['available']:
        st.error(metadata['exposure_reason']+'. Calculation controls are hidden until matching executed evidence is available.');return
    if chosen=='general_pressure':
        st.info('The existing general solver supports reviewed loops, pumps, tanks, valves, PDA/EPS and seven scenario types. Its native library readiness is checked on Network Review.')
        st.button('Open general pressure-network solver',on_click=_open_pressure);return
    basis=get_basis(conn,pid);revision=basis['revision'] if basis else 0
    scope=f'engineering_{pid}_{project["code_id"]}_{project["code_edition"]}_{revision}_{chosen}'
    template=json.loads((ROOT/'examples/engineering'/f'{chosen}.json').read_text(encoding='utf-8'))
    template.update(code_id=project['code_id'],code_edition=project['code_edition'] or template['code_edition'])
    upload=st.file_uploader('Upload engineering input package (including catalogue sources)',type=['json'],max_upload_size=10,key=scope+'_upload')
    try:
        package=json.loads(upload.getvalue().decode('utf-8-sig')) if upload else deepcopy(template)
        if package.get('module')!=chosen:raise ValueError('Uploaded package module must match the selected module')
        key=scope+'_'+digest(package)[:12]
        if not upload:st.info('Loaded a fictional software example. Replace the inputs and source records with reviewed project/code/manufacturer data before design use.')
        package['basis_reference']=st.text_area('Calculation basis and assumptions',package['basis_reference'],key=key+'_basis')
        package['code_edition']=st.text_input('Declared code edition',package['code_edition'],key=key+'_edition')
        st.caption('Source records — reviewer status is recorded as supplied; no authentication or engineering approval is inferred.')
        source_frame=st.data_editor(pd.DataFrame(package['sources']),num_rows='dynamic',key=key+'_sources',width='stretch',alt='Explicit calculation source documents, revisions, locators and supplied verification states')
        package['sources']=[clean(row) for row in source_frame.to_dict('records')]
        mode=st.radio('Engineering input method',['Interactive fields and tables','Structured input JSON'],horizontal=True,key=key+'_mode')
        if mode=='Interactive fields and tables':
            with st.expander('Calculation inputs',expanded=True):package['data']=edit_data(package['data'],key+'_data')
        else:
            package['data']=json.loads(st.text_area('Engineering calculation data (JSON)',json.dumps(package['data'],indent=2),height=320,key=key+'_raw'))
        package=validate_envelope(package)
        if package['code_id']!=project['code_id'] or project['code_edition'] and package['code_edition']!=project['code_edition']:raise ValueError('Input code/edition must match the active project basis')
    except (ValueError,TypeError,KeyError,UnicodeError) as error:
        st.error('Input/source data needs correction: '+str(error));return
    token=digest(package)
    st.download_button('Download engineering input package',json.dumps(package,indent=2),file_name=chosen+'-input.json',mime='application/json')
    if st.button('Calculate scoped engineering result',key=scope+'_run'):
        st.session_state.pop(scope+'_result',None)
        try:st.session_state[scope+'_result']=run_module(package)
        except (ValueError,TypeError,KeyError) as error:st.error(str(error))
    report=st.session_state.get(scope+'_result')
    if report and report['input_sha256']!=token:st.info('Inputs or sources changed. Recalculate before reviewing or saving results.');return
    if report:
        st.metric('Supplied-criteria technical result',report['technical_status'])
        source_label={'SYNTHETIC':'fictional software example','UNVERIFIED':'unverified source records','REVIEWED_AS_REPORTED':'reviewed as reported by the source provider'}[report['source_status']]
        st.caption('Sources: '+source_label+'. Engineering review required. Code compliance not evaluated. Calculation scope is partial.')
        st.dataframe([{'Result':label(k),'Value':str(v),'Unit':report['units'][k]} for k,v in report['values'].items()],width='stretch',alt='Calculated engineering values with explicit units')
        if report['checks']:st.dataframe([dict(c,actual=json.dumps(c['actual']),limit=json.dumps(c['limit'])) for c in report['checks']],width='stretch',alt='Each supplied engineering criterion, comparison, status and source binding')
        if report['trace']:
            st.dataframe(report['trace'],width='stretch',alt='Engineering intermediate results or source-candidate rejection reasons')
            frame=pd.DataFrame(report['trace'])
            if chosen=='pump_system':
                chart=frame.sort_values('flow_lps').rename(columns={'flow_lps':'Flow (L/s)','system_head_m':'System head (m)','pump_head_m':'Pump head (m)'})
                st.line_chart(chart,x='Flow (L/s)',y=['System head (m)','Pump head (m)'],alt='Supplied pump head and quadratic system head versus flow L/s')
            if chosen=='storm_storage':st.line_chart(frame,x='time_s',y=['inflow_lps','outflow_lps'],alt='Routed inflow and outflow hydrographs in L/s over time in seconds')
        for note in report['notes']:st.caption('• '+note)
        st.download_button('Download engineering result and evidence',json.dumps(report,indent=2,allow_nan=False),file_name=chosen+'-findings.json',mime='application/json')
        with st.form(scope+'_save_form'):
            record_id=st.text_input('Engineering calculation record ID',value=chosen+'-1')
            actor=st.text_input('Recorded by / engineering reviewer')
            if st.form_submit_button('Save engineering review record'):
                try:st.success('Saved: '+save_module_result(conn,pid,record_id,actor,report))
                except ValueError as error:st.error(str(error))
