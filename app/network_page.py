"""Review explicit, mapped networks; raw CAD/IFC ingestion is a separate adapter."""
import json
from pathlib import Path
import streamlit as st

from app.network_editor import parse_network, network_tables
from app.network_preview import render_network_preview
from app.db_helpers import next_calc_id,save_calculation
from calculations.network import analyze_water_network,analyze_drainage_network
from database.design_table_api import get_demand_from_wsfu
from models import CalculationResult,MissingCodeDataError

ROOT=Path(__file__).resolve().parents[1]


def page_network_review():
    st.header('Network design review')
    pid=st.session_state.get('project_id')
    if not pid:
        st.info('Create or open a project first.');return
    conn=st.session_state.conn
    code=conn.execute('SELECT code_id FROM projects WHERE project_id=?',(pid,)).fetchone()[0]
    st.info('Examples use synthetic criteria and catalogues. Replace them with reviewed project/manufacturer '
            'data. Edit mapped nodes and pipes below, or import JSON. Drawing intake is available on CAD / IFC Checks; '
            'it does not automatically supply a complete mapped network.')
    kind=st.selectbox('Network type',['Domestic water','Drainage and vents','General pressure network'],key='network_kind')
    from compliance.governance import get_basis
    basis=get_basis(conn,pid)
    revision=basis['revision'] if basis else 0
    if kind=='General pressure network':
        from app.general_network_page import page_general_network
        page_general_network(conn,pid,code,revision)
        return
    example='water_network.json' if kind=='Domestic water' else 'drainage_network.json'
    template=json.loads((ROOT/'examples'/example).read_text(encoding='utf-8'))
    template['code_id']=code
    scope=f'{pid}_{revision}_{code}_{kind}'
    if st.session_state.get('_network_scope') != scope:
        st.session_state.pop('network_result', None)
        st.session_state['_network_scope'] = scope
    draft_key = 'network_draft_' + scope
    model = st.session_state.setdefault(draft_key, template)
    mode = st.radio('Network input method', ['Editable tables', 'Mapped network JSON'], horizontal=True)
    preview = st.container()
    model_error = None
    if mode == 'Mapped network JSON':
        upload = st.file_uploader('Import mapped network JSON', type=['json'], max_upload_size=20, key='network_upload_' + scope)
        with st.expander('Advanced JSON editor', expanded=False):
            st.caption('JSON is the source data. Apply edits with Ctrl+Enter or leave the field to refresh the diagram above. An uploaded file takes precedence over this text.')
            text=st.text_area('Mapped network JSON', json.dumps(model, indent=2), height=300,
                          key='network_json_' + scope)
        try:
            model = parse_network(upload.getvalue().decode('utf-8-sig') if upload else text, code)
            if st.button('Load JSON into editable tables'):
                st.session_state[draft_key] = model
                st.session_state['network_editor_generation_' + scope] = st.session_state.get('network_editor_generation_' + scope, 0) + 1
                st.success('JSON loaded. Select Editable tables to edit the imported network.')
        except (ValueError, TypeError, UnicodeError) as error:
            model_error = str(error)
            st.error(model_error)
    else:
        try:
            generation = st.session_state.get('network_editor_generation_' + scope, 0)
            model = network_tables(model, scope + str(generation), kind == 'Domestic water')
        except (ValueError, TypeError, KeyError) as error:
            model_error = str(error)
            st.error(model_error)
    with preview:
        render_network_preview(model, model_error)
    st.download_button('Download mapped network JSON', json.dumps(model, indent=2),
                       file_name='mapped-network.json', mime='application/json', disabled=bool(model_error))
    select=st.checkbox('Select available catalogue sizes against velocity and pressure',value=False,
                       disabled=kind!='Domestic water')
    if st.button('Run network review'):
        try:
            if model_error:
                raise ValueError(model_error)
            model = parse_network(json.dumps(model), code)
            network_id=model.get('network_id')
            if not isinstance(network_id,str) or not network_id.strip(): raise ValueError('network_id is required')
            if kind=='Domestic water':
                control=model.get('control_type','flush_tank')
                if control not in ('flush_tank','flush_valve'): raise ValueError('Unsupported demand control type')
                def demand(wsfu):
                    d=get_demand_from_wsfu(conn,code,wsfu,control+'_lpm')
                    if d is None: raise MissingCodeDataError('Demand table/range',f'code={code}, WSFU={wsfu}')
                    return dict(flow_lps=d.value/60,unit='L/s',reference=d.table_reference,
                                confidence=d.confidence,notes=d.notes)
                report=analyze_water_network(model,demand_lookup=demand,select_sizes=select)
                calc_type='water_network_check';value=report['minimum_pressure_margin_m'];unit='m pressure margin'
                formula='Explicit tree design envelope: Q from declared demand; losses + elevation + required outlet head'
            else:
                report=analyze_drainage_network(conn,code,model)
                calc_type='drainage_network_check';value=report['total_drainage_dfu'];unit='DFU'
                formula='Accumulate DFU toward outlet; selected-code context capacity, actual fall/slope and supported vent checks'
            result=CalculationResult(next_calc_id(conn,pid,calc_type),calc_type,formula,
                {'network':model},report,value,unit,status=report['technical_status'],
                reference=f'{code}; explicit source references in every network criterion/result',
                notes='; '.join(report['limitations']))
            save_calculation(conn,pid,result,target_type='network',target_id=network_id)
            report['calc_id']=result.calc_id
            st.session_state['network_result']=report
        except (ValueError,TypeError,KeyError,MissingCodeDataError) as error:
            st.session_state.pop('network_result',None)
            st.error(str(error))
    report=st.session_state.get('network_result')
    if report:
        st.subheader('Last saved review')
        st.caption(f"Calculation: {report['calc_id']}")
        st.metric('Technical result', report['technical_status'])
        st.metric('Engineering review', report['review_status'])
        with st.expander('Input verification hash'):
            st.code(report['input_sha256'], language=None)
        st.caption('This is the last submitted network. Run again after changing network inputs.')
        st.dataframe(report['pipes'],width='stretch',alt='Per-pipe design checks and references')
        if report.get('terminals'):
            st.dataframe(report['terminals'],width='stretch',alt='All supply-to-terminal pressure paths and margins')
        if report.get('vents'):
            st.dataframe(report['vents'],width='stretch',alt='Vent sizing and unsupported arrangement findings')
        for limitation in report['limitations']: st.caption(limitation)
        st.download_button('Download network findings',json.dumps(report,indent=2),
                           file_name='network-findings.json',mime='application/json')
