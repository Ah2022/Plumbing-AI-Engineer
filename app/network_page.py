"""Review explicit, mapped networks; raw CAD/IFC ingestion is a separate adapter."""
import json
from pathlib import Path
import streamlit as st

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
            'data. This page reads mapped network JSON; it does not yet scan raw CAD or IFC files.')
    kind=st.selectbox('Network type',['Domestic water','Drainage and vents'])
    if st.session_state.get('_network_kind')!=kind:
        st.session_state.pop('network_result',None)
        st.session_state['_network_kind']=kind
    from compliance.governance import get_basis
    basis=get_basis(conn,pid)
    revision=basis['revision'] if basis else 0
    example='water_network.json' if kind=='Domestic water' else 'drainage_network.json'
    template=json.loads((ROOT/'examples'/example).read_text(encoding='utf-8'))
    template['code_id']=code
    text=st.text_area('Mapped network JSON',json.dumps(template,indent=2),height=400,key=f'network_json_{pid}_{revision}_{code}_{kind}')
    select=st.checkbox('Select available catalogue sizes against velocity and pressure',value=False,
                       disabled=kind!='Domestic water')
    if st.button('Run network review'):
        try:
            def reject_constant(value): raise ValueError('Non-finite JSON constant: '+value)
            model=json.loads(text,parse_constant=reject_constant)
            if not isinstance(model,dict) or model.get('code_id')!=code:
                raise ValueError('Network code_id must match the active project code')
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
        st.write(dict(calc_id=report['calc_id'],technical_status=report['technical_status'],
                      review_status=report['review_status'],input_sha256=report['input_sha256']))
        st.caption('This is the last submitted network. Run again after editing the draft JSON.')
        st.dataframe(report['pipes'],width='stretch',alt='Per-pipe design checks and references')
        if report.get('terminals'):
            st.dataframe(report['terminals'],width='stretch',alt='All supply-to-terminal pressure paths and margins')
        if report.get('vents'):
            st.dataframe(report['vents'],width='stretch',alt='Vent sizing and unsupported arrangement findings')
        for limitation in report['limitations']: st.caption(limitation)
        st.download_button('Download network findings',json.dumps(report,indent=2),
                           file_name='network-findings.json',mime='application/json')
