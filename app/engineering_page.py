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
        '_m05_s':'m^0.5/s','_m_s':'m/s','_lps':'L/s','_lpm':'reference L/min','_kg_s':'kg/s','_mpa':'MPa','_kpa':'kPa','_m3':'m³','_m2':'m²','_mm':'mm','_pa':'Pa','_pct':'%',
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
        elif isinstance(value,str):
            if name=='standard_basis':
                from engineering.medical_gas import BASIS
                result[name]=st.selectbox(label(name),list(BASIS),index=list(BASIS).index(value),format_func=BASIS.get,key=widget)
            else:result[name]=st.text_input(label(name),value=value,key=widget)
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
    from app.workspace import go
    go('Network Review')
    st.session_state['network_kind']='General pressure network'


def open_engineering_module(identity):
    from app.workspace import go
    go('Engineering Modules')
    st.session_state['engineering_module_choice']=identity


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
    chosen=st.selectbox('Engineering module',list(lookup),format_func=lambda k:f"{lookup[k]['priority']}. {lookup[k]['title']}",key='engineering_module_choice')
    metadata=lookup[chosen]
    st.subheader(metadata['title'])
    if metadata.get('development_stage'):
        st.warning('Experimental research implementation. Analytical software checks are available; laboratory, manufacturer and independent engineering validation remain pending. Read the limits before interpreting results.')
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
    if chosen=='pressure_zones':
        from solvers.graph import normalize_graph
        from solvers.service import fingerprint
        template['data']['model']['code_id']=project['code_id']
        normalized,_=normalize_graph(template['data']['model'])
        template['data']['solver_report'].update(normalized_model=normalized,input_sha256=fingerprint(normalized))
    upload=st.file_uploader('Upload engineering input package (including catalogue sources)',type=['json'],max_upload_size=10,key=scope+'_upload')
    try:
        package=json.loads(upload.getvalue().decode('utf-8-sig')) if upload else deepcopy(template)
        if package.get('module')!=chosen:raise ValueError('Uploaded package module must match the selected module')
        if chosen in ('equipment_selection','relief_selection'):
            from engineering.catalogue import import_catalogue,export_catalogue
            kind='relief' if chosen=='relief_selection' else package['data']['equipment_kind']
            with st.expander('Import manufacturer catalogue CSV (explicit SI units)'):
                st.caption('Use the two downloaded templates for pump models and H–Q points, or one for tanks/relief devices. Bind every source_id to a manufacturer source record below. Examples contain fictional ratings.')
                model_csv,curve_csv=export_catalogue(package['data']['catalogue'],kind)
                st.download_button('Download catalogue CSV template',model_csv,file_name=kind+'-models.csv',mime='text/csv')
                if curve_csv is not None:st.download_button('Download pump curve CSV template',curve_csv,file_name='pump-curves.csv',mime='text/csv')
                csvfile=st.file_uploader('Catalogue models (CSV)',type=['csv'],max_upload_size=2,key=scope+'_model_csv')
                curvefile=st.file_uploader('Pump H–Q points (CSV)',type=['csv'],max_upload_size=2,key=scope+'_curve_csv') if kind=='pump' else None
                if csvfile:
                    package['data']['catalogue']=import_catalogue(csvfile.getvalue(),kind,curvefile.getvalue() if curvefile else None)
        key=scope+'_'+digest(package)[:12]
        if not upload:st.info('Loaded a fictional software example. Replace the inputs and source records with reviewed project/code/manufacturer data before design use.')
        package['basis_reference']=st.text_area('Calculation basis and assumptions',package['basis_reference'],key=key+'_basis')
        package['code_edition']=st.text_input('Declared code edition',package['code_edition'],key=key+'_edition')
        st.caption('Source records — reviewer status is recorded as supplied; no authentication or engineering approval is inferred.')
        source_frame=st.data_editor(pd.DataFrame(package['sources']),num_rows='dynamic',key=key+'_sources',width='stretch',alt='Explicit calculation source documents, revisions, locators and supplied verification states')
        package['sources']=[clean(row) for row in source_frame.to_dict('records')]
        modes=['Structured input JSON','Interactive fields and tables'] if chosen=='pressure_zones' else ['Interactive fields and tables','Structured input JSON']
        mode=st.radio('Engineering input method',modes,horizontal=True,key=key+'_mode')
        if mode=='Interactive fields and tables':
            with st.expander('Calculation inputs',expanded=True):package['data']=edit_data(package['data'],key+'_data')
        else:
            package['data']=json.loads(st.text_area('Engineering calculation data (JSON)',json.dumps(package['data'],indent=2),height=320,key=key+'_raw'))
        if chosen in ('equipment_selection','relief_selection','liquid_gas_inventory'):
            from engineering.source_authentication import source_payload,canonical
            import base64
            with st.expander('Authenticate source document and numerical data'):
                st.caption('Verification requires a detached Ed25519 attestation and an independently enrolled server trust key. A checksum alone does not authenticate a manufacturer, and reviewer attestations remain distinct from manufacturer releases. Maximum source document size: 2 MB.')
                ids=sorted({r['source_id'] for r in package['data'].get('vaporizers' if chosen=='liquid_gas_inventory' else 'catalogue',[])})
                if ids:
                    source_id=st.selectbox('Source to authenticate',ids,key=scope+'_auth_source')
                    st.download_button('Download exact source/data signing payload',canonical(source_payload(package,source_id)),file_name='source-data-payload.json',mime='application/json')
                    attfile=st.file_uploader('Detached source attestation (JSON)',type=['json'],max_upload_size=1,key=scope+'_attestation')
                    docfile=st.file_uploader('Attested source document',type=['pdf','json','csv','txt'],max_upload_size=2,key=scope+'_attested_document')
                    if attfile:
                        att=json.loads(attfile.getvalue().decode('utf-8-sig'))
                        if not isinstance(att,dict) or att.get('source_id')!=source_id:raise ValueError('Attestation source_id must match the selected source')
                        if not docfile:raise ValueError('Attach the exact source document named by the signed checksum')
                        att['document_base64']=base64.b64encode(docfile.getvalue()).decode('ascii')
                        package['source_attestations']=[a for a in package.get('source_attestations',[]) if a.get('source_id')!=source_id]+[att]
        if chosen=='pressure_zones':
            from solvers.service import solve_network
            modeltoken=digest(package['data']['model'])
            st.caption('The bundled report is an explicitly fictional hand reference. Regenerate a native EPANET report after editing the network. No delivered flow is adjusted after hydraulic solution.')
            if st.button('Solve current model with EPANET for zone review',key=scope+'_native_zones'):
                native=solve_network(package['data']['model'],backend='epanet')
                st.session_state[scope+'_native_zone_report']=(modeltoken,native)
                if not native.get('complete'):st.error('EPANET did not complete: '+str(native.get('diagnostics',[])))
            cached=st.session_state.get(scope+'_native_zone_report')
            if cached and cached[0]==modeltoken:package['data']['solver_report']=cached[1]
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
        auth=report.get('source_authentication',{})
        st.caption('Source authentication: '+auth.get('status','NOT_PROVIDED')+'. Signer role and content integrity do not confer engineering acceptance.')
        if auth.get('sources'):st.dataframe(auth['sources'],width='stretch',alt='Authenticated source IDs, signer roles, document/data checksums and explicit trust limitations')
        st.dataframe([{'Result':label(k),'Value':str(v),'Unit':report['units'][k]} for k,v in report['values'].items()],width='stretch',alt='Calculated engineering values with explicit units')
        if report['checks']:st.dataframe([dict(c,actual=json.dumps(c['actual']),limit=json.dumps(c['limit'])) for c in report['checks']],width='stretch',alt='Each supplied engineering criterion, comparison, status and source binding')
        if report['trace']:
            st.dataframe(report['trace'],width='stretch',alt='Engineering intermediate results or source-candidate rejection reasons')
            frame=pd.DataFrame(report['trace'])
            if chosen=='pump_system':
                chart=frame.sort_values('flow_lps').rename(columns={'flow_lps':'Flow (L/s)','system_head_m':'System head (m)','pump_head_m':'Pump head (m)'})
                st.line_chart(chart,x='Flow (L/s)',y=['System head (m)','Pump head (m)'],alt='Supplied pump head and quadratic system head versus flow L/s')
            if chosen=='storm_storage':st.line_chart(frame,x='time_s',y=['inflow_lps','outflow_lps'],alt='Routed inflow and outflow hydrographs in L/s over time in seconds')
            if chosen=='recirculation_network':
                times=frame[frame['kind']=='time']
                st.line_chart(times,x='time_s',y=['return_temperature_c','minimum_water_temperature_c'],alt='Recirculation return and minimum distribution temperatures over time')
            if chosen in ('coupled_drainage','hot_water_draw','pressure_zones'):
                kind={'coupled_drainage':'chamber','hot_water_draw':'layer','pressure_zones':'zone_service'}[chosen]
                values=frame[frame['kind']==kind]
                if not values.empty:
                    selected=st.selectbox('Research result object',list(values['id'].unique()),key=scope+'_research_trace_object')
                    values=values[values['id']==selected]
                    column={'coupled_drainage':'air_gauge_pa','hot_water_draw':'temperature_c','pressure_zones':'pressure_m'}[chosen]
                    st.line_chart(values,x='time_s',y=column,alt='Selected experimental model object result over time; declared units and limits apply')
            if chosen in ('network_transient','dynamic_drainage','drainage_air'):
                kind='node' if chosen=='network_transient' else 'air_node' if chosen=='drainage_air' else 'pipe'
                values=frame[frame['kind']==kind]
                selected=st.selectbox('Result object',list(values['id'].unique()),key=scope+'_trace_object')
                values=values[values['id']==selected]
                y='gauge_kpa' if chosen=='network_transient' else 'gauge_pa' if chosen=='drainage_air' else 'flow_lps'
                st.line_chart(values,x='time_s',y=y,alt='Selected object hydraulic result over time with declared units')
        for note in report['notes']:st.caption('• '+note)
        st.download_button('Download engineering result and evidence',json.dumps(report,indent=2,allow_nan=False),file_name=chosen+'-findings.json',mime='application/json')
        with st.form(scope+'_save_form'):
            record_id=st.text_input('Engineering calculation record ID',value=chosen+'-1')
            actor=st.text_input('Recorded by / engineering reviewer')
            if st.form_submit_button('Save engineering review record'):
                try:st.success('Saved: '+save_module_result(conn,pid,record_id,actor,report))
                except ValueError as error:st.error(str(error))
